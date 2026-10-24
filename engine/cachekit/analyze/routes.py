"""Route grouping preserves explicit call sites and normalizes tool ordering."""

import hashlib
import re

from cachekit.models import RequestRecord
from cachekit.render.canonical import segments
from cachekit.serialization import canonical_json


def group_routes(records: list[RequestRecord], prefix_chars: int) -> dict[str, list[RequestRecord]]:
    groups: dict[str, list[RequestRecord]] = {}
    for record in sorted(records, key=lambda r: (r.ts, r.id)):
        route = record.route
        if route is None:
            system = "\n".join(s.text for s in segments(record) if s.role == "system")
            # Normalize obvious volatile forms, retaining meaningful template labels.
            masked = re.sub(r"[0-9a-fA-F]{8,}", "<hex>", system[:prefix_chars])
            masked = re.sub(r"\d+", "#", masked)
            tool_set = sorted(canonical_json(tool) for tool in record.tools or [])
            digest = hashlib.sha256(canonical_json([tool_set, masked]).encode()).hexdigest()[:16]
            route = f"inferred:{digest}"
        groups.setdefault(route, []).append(record)
    return dict(sorted(groups.items()))
