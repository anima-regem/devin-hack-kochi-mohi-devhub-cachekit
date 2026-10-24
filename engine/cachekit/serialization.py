"""Pure, canonical JSON serialization. Never reorder request lists or tools."""

import json

from pydantic import BaseModel, JsonValue


def canonical_json(value: BaseModel | JsonValue) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
