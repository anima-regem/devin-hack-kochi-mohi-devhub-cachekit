"""Deterministic line alignment, refined to character spans on scalar lines.

Line anchors prevent repeated words in a long policy from pulling an alignment
into unrelated text. Empty lines do not split variable example/context blocks.
Raw values are internal only; report previews and evidence must be redacted.
"""

import json
import re
from bisect import bisect_left, bisect_right
from difflib import SequenceMatcher

from pydantic import Field

from cachekit.models import BoundaryModel

VOLATILE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
    r"|\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    r"|\b[0-9a-fA-F]{16,}\b"
)
FIELD_LINE = re.compile(
    r"(?i)^\s*(?:current time|timestamp|date|request[_ ]?id|customer|user|name|email|"
    r"locale|language):"
)


class VariableSpan(BoundaryModel):
    start: int
    end: int
    values: dict[str, str]
    ranges: dict[str, tuple[int, int]]
    label: str = "unknown"
    safe_to_move: bool = False


class SegmentTemplate(BoundaryModel):
    key: str
    kind: str
    index: int
    role: str | None
    baseline_id: str
    text: str
    spans: list[VariableSpan] = Field(default_factory=list)

    def stable_ranges(self) -> list[tuple[int, int]]:
        cursor = 0
        result: list[tuple[int, int]] = []
        for span in self.spans:
            if span.start > cursor:
                result.append((cursor, span.start))
            cursor = max(cursor, span.end)
        if cursor < len(self.text):
            result.append((cursor, len(self.text)))
        return result


def _mask(line: str) -> str:
    return re.sub(r"\d+", "#", VOLATILE.sub("<volatile>", line))


def _offsets(lines: list[str]) -> list[int]:
    result = [0]
    for line in lines:
        result.append(result[-1] + len(line))
    return result


def _boundary(ops: list[tuple], index: int, *, right: bool) -> int:
    for tag, a, b, c, d in ops:
        if tag == "insert" and a == index:
            return d if right else c
        if a <= index < b:
            if b - a == d - c:
                return c + index - a
            if index == a:
                return c
            return d if right else c
    return ops[-1][4] if ops else 0


def _affixes(values: list[str]) -> tuple[int, int]:
    shortest = min(map(len, values))
    prefix = 0
    while prefix < shortest and len({v[prefix] for v in values}) == 1:
        prefix += 1
    suffix = 0
    while suffix < shortest - prefix and len({v[-1 - suffix] for v in values}) == 1:
        suffix += 1
    return prefix, suffix


def _equal_json(values: list[str]) -> bool:
    try:
        parsed = [json.loads(v) for v in values]
        return all(isinstance(v, (dict, list)) for v in parsed) and all(
            v == parsed[0] for v in parsed
        )
    except (ValueError, TypeError):
        return False


def extract_template(
    texts: dict[str, str], *, key: str, kind: str, index: int, role: str | None
) -> SegmentTemplate:
    baseline_id = min(texts)
    baseline = texts[baseline_id]
    lines = baseline.splitlines(keepends=True)
    offsets = _offsets(lines)
    keys = [_mask(line) for line in lines]
    stable = [True] * len(lines)
    alignments: dict[str, tuple[list[str], list[int], list[tuple]]] = {}
    insertions: set[int] = set()
    for record_id, text in sorted(texts.items()):
        other = text.splitlines(keepends=True)
        ops = SequenceMatcher(
            None, keys, [_mask(line) for line in other], autojunk=False
        ).get_opcodes()
        alignments[record_id] = (other, _offsets(other), ops)
        for tag, a, b, c, d in ops:
            if tag == "insert":
                insertions.add(a)
            for i in range(a, b):
                same = b - a == d - c and lines[i] == other[c + i - a]
                stable[i] = stable[i] and same
    groups: list[tuple[int, int]] = []
    begin: int | None = None
    last_changed = 0
    for i, line in enumerate(lines):
        # Keep changing scalar fields apart, but keep few-shot dialogue together.
        next_is_agent = i + 1 < len(lines) and re.match(r"(?i)\s*(agent|assistant):", lines[i + 1])
        field = bool(FIELD_LINE.match(line)) and not next_is_agent
        if not stable[i] and field:
            if begin is not None:
                groups.append((begin, last_changed))
                begin = None
            groups.append((i, i + 1))
        elif not stable[i]:
            if begin is None:
                begin = i
            last_changed = i + 1
        elif line.strip() and begin is not None:
            groups.append((begin, last_changed))
            begin = None
    if begin is not None:
        groups.append((begin, last_changed))
    groups.extend((i, i) for i in insertions if not any(a <= i <= b for a, b in groups))
    spans: list[VariableSpan] = []
    for a, b in sorted(set(groups)):
        ranges: dict[str, tuple[int, int]] = {}
        values: dict[str, str] = {}
        for record_id, (_other, pos, ops) in alignments.items():
            left = _boundary(ops, a, right=False)
            right = _boundary(ops, b, right=True)
            ranges[record_id] = (pos[left], pos[max(left, right)])
            values[record_id] = texts[record_id][ranges[record_id][0] : ranges[record_id][1]]
        if len(set(values.values())) < 2:
            continue
        start, end = offsets[a], offsets[b]
        all_values = list(values.values())
        # Refine scalar lines, but preserve whole JSON objects for semantic comparison.
        if (
            b - a == 1
            and all(v.count("\n") <= 1 for v in all_values)
            and not _equal_json(all_values)
        ):
            prefix, suffix = _affixes(all_values)
            for match in VOLATILE.finditer(baseline[start:end]):
                if match.start() < end - start - suffix and match.end() > prefix:
                    prefix = min(prefix, match.start())
                    suffix = min(suffix, end - start - match.end())
            if prefix + suffix < len(baseline[start:end]):
                start += prefix
                end -= suffix
                for record_id, (left, right) in ranges.items():
                    ranges[record_id] = (left + prefix, right - suffix)
                    values[record_id] = texts[record_id][left + prefix : right - suffix]
        spans.append(VariableSpan(start=start, end=end, values=values, ranges=ranges))
    return SegmentTemplate(
        key=key,
        kind=kind,
        index=index,
        role=role,
        baseline_id=baseline_id,
        text=baseline,
        spans=spans,
    )


def project_remaining(template: SegmentTemplate, texts: dict[str, str]) -> None:
    """Map sampled spans onto remaining requests; never fabricate their values."""
    baseline_lines = template.text.splitlines(keepends=True)
    base_pos = _offsets(baseline_lines)
    for record_id, text in sorted(texts.items()):
        if all(record_id in span.ranges for span in template.spans):
            continue
        lines = text.splitlines(keepends=True)
        pos = _offsets(lines)
        ops = SequenceMatcher(
            None, [_mask(v) for v in baseline_lines], [_mask(v) for v in lines], autojunk=False
        ).get_opcodes()
        for span in template.spans:
            first = max(0, bisect_right(base_pos, span.start) - 1)
            last = bisect_left(base_pos, span.end)
            left_line = _boundary(ops, first, right=False)
            right_line = _boundary(ops, last, right=True)
            left = min(len(text), pos[left_line] + span.start - base_pos[first])
            right = max(left, pos[right_line] - (base_pos[last] - span.end))
            right = min(len(text), right)
            span.ranges[record_id] = (left, right)
            span.values[record_id] = text[left:right]
