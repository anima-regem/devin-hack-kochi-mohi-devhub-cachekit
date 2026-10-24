"""Structural checks do not use application-specific planted metadata."""

from collections import defaultdict

from cachekit.models import BoundaryModel, RequestRecord
from cachekit.serialization import canonical_json


class StructuralBreaker(BoundaryModel):
    breaker: str
    request_ids: list[str]
    message_index: int | None = None


def structural_breakers(records: list[RequestRecord]) -> list[StructuralBreaker]:
    result: list[StructuralBreaker] = []
    signatures = [tuple(sorted(canonical_json(t) for t in r.tools or [])) for r in records]
    ordered = [canonical_json(r.tools) for r in records]
    if len(set(signatures)) == 1 and len(set(ordered)) > 1:
        result.append(StructuralBreaker(breaker="tool_order", request_ids=[r.id for r in records]))
    elif len(set(signatures)) > 1:
        result.append(
            StructuralBreaker(breaker="tool_set_varies", request_ids=[r.id for r in records])
        )
    sessions: dict[str, list[RequestRecord]] = defaultdict(list)
    for record in records:
        if record.session_id is not None:
            sessions[record.session_id].append(record)
    truncations: list[str] = []
    rewrites: list[str] = []
    for session in sorted(sessions):
        items = sorted(sessions[session], key=lambda r: (r.ts, r.id))
        for previous, current in zip(items, items[1:], strict=False):
            before = [m for m in previous.messages if m.role != "system"]
            after = [m for m in current.messages if m.role != "system"]
            if not before or after[: len(before)] == before:
                continue
            overlap = any(
                after[: len(before) - drop] == before[drop:] for drop in range(1, len(before))
            )
            if overlap:
                truncations.append(current.id)
            elif len(before) == len(after) and len(before) >= 3:
                rewrites.append(current.id)
    if truncations:
        result.append(
            StructuralBreaker(breaker="history_truncation", request_ids=sorted(truncations))
        )
    if rewrites:
        result.append(StructuralBreaker(breaker="history_rewrite", request_ids=sorted(rewrites)))
    tenants = {str(r.meta["tenant_id"]) for r in records if r.meta.get("tenant_id") is not None}
    unsalted = [
        r.id
        for r in records
        if r.meta.get("tenant_id") is not None and not r.params.get("cache_salt")
    ]
    if len(tenants) > 1 and unsalted:
        result.append(StructuralBreaker(breaker="cross_tenant_shared_prefix", request_ids=unsalted))
    return result
