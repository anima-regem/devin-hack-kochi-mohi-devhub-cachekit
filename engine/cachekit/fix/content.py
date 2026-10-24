"""Pure, conservative content preservation checks; never emit prompt text."""

import re
from collections import Counter

from cachekit.analyze.template import SegmentTemplate
from cachekit.fix.models import ContentResult
from cachekit.models import Message, RequestRecord
from cachekit.render.canonical import text_content
from cachekit.serialization import canonical_json


def _lines(record: RequestRecord) -> Counter:
    # This check establishes textual preservation only, not instruction authority.
    result: Counter = Counter()
    if record.system is not None:
        for line in text_content(record.system).splitlines():
            if line.strip():
                result[re.sub(r"\s+", " ", line).strip()] += 1
    for message in record.messages:
        for line in text_content(message.content).splitlines():
            if line.strip():
                result[re.sub(r"\s+", " ", line).strip()] += 1
    return result


def check_content(
    before: list[RequestRecord],
    after: list[RequestRecord],
    templates: list[SegmentTemplate],
    recorded_histories: dict[str, list[Message]] | None = None,
) -> ContentResult:
    old = {r.id: r for r in before}
    new = {r.id: r for r in after}
    missing = added = dynamic_missing = 0
    restored = unexpected = 0
    roles_equal = True
    tools_equal = set(old) == set(new)
    envelope_equal = tools_equal
    for key in sorted(set(old) | set(new)):
        if key not in old or key not in new:
            missing += int(key not in new)
            added += int(key not in old)
            continue
        a, b = old[key], new[key]
        first, second = _lines(a), _lines(b)
        missing += sum((first - second).values())
        additions = second - first
        added += sum(additions.values())
        history = (recorded_histories or {}).get(key, [])
        historical = RequestRecord(
            id="history", ts=0, messages=history or [Message(role="user", content="")]
        )
        retained = RequestRecord(
            id="retained",
            ts=0,
            messages=[m for m in a.messages if m.role != "system"][:-1]
            or [Message(role="user", content="")],
        )
        permitted = _lines(historical) - _lines(retained)
        restored += sum((additions & permitted).values())
        unexpected += sum((additions - permitted).values())

        def conversation_lines(record):
            return Counter(
                (m.role, re.sub(r"\s+", " ", line).strip())
                for m in record.messages
                if m.role != "system"
                for line in text_content(m.content).splitlines()
                if line.strip()
            )

        roles_equal &= not (conversation_lines(a) - conversation_lines(b))
        tools_equal &= Counter(canonical_json(t) for t in a.tools or []) == Counter(
            canonical_json(t) for t in b.tools or []
        )
        envelope_equal &= (a.ts, a.session_id, a.route, a.provider, a.model, a.params) == (
            b.ts,
            b.session_id,
            b.route,
            b.provider,
            b.model,
            b.params,
        )
        # Role changes require the independent behavioral gate and human review.
        texts = [text_content(m.content) for m in b.messages]
        if b.system is not None:
            texts.append(text_content(b.system))
        for template in templates:
            for span in template.spans:
                value = span.values.get(key)
                if value and not any(value in text for text in texts):
                    dynamic_missing += 1
    return ContentResult(
        passed=missing == unexpected == dynamic_missing == 0
        and tools_equal
        and envelope_equal
        and roles_equal,
        n_requests=len(before),
        missing_lines=missing,
        added_lines=added,
        restored_history_lines=restored,
        unexpected_added_lines=unexpected,
        missing_dynamic_values=dynamic_missing,
        tools_equal=tools_equal,
        envelope_equal=envelope_equal,
        conversation_roles_preserved=roles_equal,
    )
