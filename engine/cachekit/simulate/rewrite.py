"""A conservative simulated projection, never a patched AFTER application."""

import json
import re

from cachekit.analyze.template import SegmentTemplate
from cachekit.models import Message, RequestRecord
from cachekit.render.canonical import segment_key, segments
from cachekit.serialization import canonical_json


def rewrite(
    record: RequestRecord, templates: list[SegmentTemplate], *, sort_tools: bool
) -> RequestRecord:
    result = record.model_copy(deep=True)
    sources = {segment_key(s): s for s in segments(record)}
    dynamic: list[str] = []
    for template in templates:
        source = sources.get(template.key)
        if source is None:
            continue
        edits: list[tuple[int, int, str]] = []
        for span in template.spans:
            if not span.safe_to_move or record.id not in span.ranges:
                continue
            start, end = span.ranges[record.id]
            value = source.text[start:end]
            if span.label == "json_key_order":
                replacement = canonical_json(json.loads(value))
            elif span.label == "whitespace_template":
                replacement = " " if not value.strip() else re.sub(r"\s+", " ", value)
            else:
                replacement = ""
            edits.append((start, end, replacement))
        ordered = sorted(edits)
        if any(b > c for (_, b, _), (c, _, _) in zip(ordered, ordered[1:], strict=False)):
            # An ambiguous alignment cannot justify dropping or duplicating content.
            continue
        text = source.text
        for start, end, replacement in ordered:
            if not replacement:
                dynamic.append(source.text[start:end])
        for start, end, replacement in reversed(ordered):
            text = text[:start] + replacement + text[end:]
        if template.kind == "system":
            result.system = text
        elif template.kind == "message":
            result.messages[template.index].content = text
    if sort_tools and result.tools:
        result.tools.sort(
            key=lambda t: (str(t.get("function", {}).get("name", "")), canonical_json(t))
        )
    if dynamic:
        # Keep changing values in a trailing user block; preserve their bytes and order.
        result.messages.append(
            Message(role="user", content="Context for this request:\n" + "\n".join(dynamic))
        )
    return result
