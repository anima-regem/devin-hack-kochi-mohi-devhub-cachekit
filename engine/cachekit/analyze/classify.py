"""Deterministic hole classification; never consult planted labels or agents."""

import json
import re
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime

from cachekit.analyze.template import VariableSpan
from cachekit.models import RequestRecord

TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
    r"|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}"
    r"|\b\d{1,2}/\d{1,2}/\d{4}\b"
)
UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I
)
HEX_ID = re.compile(r"\b[0-9a-f]{16,}\b", re.I)
IDENTITY = re.compile(r"(?i)(?:customer|user|name|e-?mail|locale|language|tier)\s*[:=]")

SAFE = {
    "timestamp",
    "request_id",
    "few_shot_sampling",
    "rag_before_static",
    "json_key_order",
    "whitespace_template",
}
HINTS = {
    "timestamp": "Move the timestamp after static instructions; preserve its value.",
    "request_id": (
        "Move the request identifier to trailing context or metadata; "
        "preserve required information."
    ),
    "user_identity": "Review personalization and locale semantics before moving this field.",
    "few_shot_sampling": (
        "Keep example selection/order stable where safe; preserve all required example information."
    ),
    "rag_before_static": (
        "Put static instructions before retrieved context; preserve every retrieved value."
    ),
    "json_key_order": "Serialize equivalent JSON with sorted keys and fixed separators.",
    "whitespace_template": (
        "Use one consistent whitespace template; review case and punctuation changes."
    ),
    "tool_order": "Keep the same tool set in a fixed order, such as sorting by function name.",
    "tool_set_varies": (
        "Review whether a stable full tool registry is appropriate; "
        "do not expand authority silently."
    ),
    "history_truncation": (
        "Review chunked truncation or a pinned summary; preserve required conversation context."
    ),
    "history_rewrite": (
        "Append turns instead of rewriting earlier messages; review intentional edits."
    ),
    "cross_tenant_shared_prefix": (
        "Consider a per-tenant cache_salt; this trades sharing for tenant isolation."
    ),
    "template_version": (
        "Report intentional prompt variants separately before treating them as defects."
    ),
    "unknown": "Review this changing span before moving it; no automatic rewrite is proposed.",
}


def _is_timestamp(value: str) -> bool:
    value = value.strip()
    if TIMESTAMP.fullmatch(value):
        try:
            if re.match(r"\d{4}-", value):
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                datetime.strptime(value, "%d/%m/%Y")
            return True
        except ValueError:
            return False
    if re.match(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s", value):
        try:
            parsedate_to_datetime(value)
            return True
        except (ValueError, TypeError):
            pass
    return False


def classify(
    span: VariableSpan, *, context: str, records: dict[str, RequestRecord], large_hole_chars: int
) -> str:
    if len(set(span.values.values())) > 1 and all(not v.strip() for v in span.values.values()):
        return "whitespace_template"
    values = [v for v in span.values.values() if v.strip()]
    if not values:
        return "unknown"
    if all(_is_timestamp(v) for v in values):
        return "timestamp"
    if re.search(r"(?i)(time|timestamp|date|epoch)", context) and all(
        re.fullmatch(r"\d{10}(?:\d{3})?", v.strip()) for v in values
    ):
        return "timestamp"
    if all(UUID.search(v) or HEX_ID.search(v) for v in values):
        return "request_id"
    if re.search(r"(?i)(request|trace|nonce|correlation)[_ -]?(id)?\s*[:=]", context) and all(
        re.fullmatch(r"[A-Za-z0-9_+/=-]{16,}", v.strip()) for v in values
    ):
        return "request_id"
    try:
        parsed = [json.loads(v) for v in values]
        if all(isinstance(v, (dict, list)) for v in parsed) and all(v == parsed[0] for v in parsed):
            return "json_key_order"
    except (ValueError, TypeError):
        pass
    normalized = [re.sub(r"[\W_]", "", v).casefold() for v in values]
    if len(set(normalized)) == 1:
        return "whitespace_template"
    if IDENTITY.search(context):
        sessions: dict[str, set[str]] = {}
        for record_id, value in span.values.items():
            session = records[record_id].session_id
            if session is not None:
                sessions.setdefault(session, set()).add(value)
        if sessions and all(len(v) == 1 for v in sessions.values()):
            return "user_identity"
    mean_length = sum(map(len, values)) / len(values)
    if mean_length >= large_hole_chars:
        dialogue = all(
            re.search(r"(?im)^(?:user|customer|question|Q):", v)
            and re.search(r"(?im)^(?:assistant|agent|answer|A):", v)
            for v in values
        )
        units = [part.strip() for v in values for part in re.split(r"\n\s*\n", v) if part.strip()]
        repeated_set = len(units) >= 2 * len(values) and len(set(units)) < len(units) * 0.75
        if (
            dialogue
            or repeated_set
            or re.search(r"(?i)(few.shot|examples|demonstrations)", context)
        ):
            return "few_shot_sampling"
        if len(set(values)) / len(values) >= 0.75 or re.search(
            r"(?i)(retriev|\brag\b|context)", context
        ):
            return "rag_before_static"
    return "unknown"


def tool_signature(tools: list[dict] | None) -> Counter:
    from cachekit.serialization import canonical_json

    return Counter(canonical_json(tool) for tool in tools or [])
