"""Strict native JSONL loading with safe errors and exact input hashes."""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from cachekit.models import RequestRecord
from cachekit.serialization import canonical_json


def read_requests(path: Path) -> tuple[list[RequestRecord], str]:
    return parse_requests(path.read_bytes())


def parse_requests(raw: bytes) -> tuple[list[RequestRecord], str]:
    """Validate uploaded bytes locally using the same contract as file ingestion."""
    records: list[RequestRecord] = []
    seen: set[str] = set()
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = RequestRecord.model_validate_json(line)
        except ValidationError:
            raise ValueError(
                f"Invalid RequestRecord on line {number}; input content withheld"
            ) from None
        if record.id in seen:
            raise ValueError(f"Duplicate request ID on line {number}; input content withheld")
        seen.add(record.id)
        records.append(record)
    return records, hashlib.sha256(raw).hexdigest()


def write_requests(records: list[RequestRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda record: (record.ts, record.id))
    path.write_text("".join(canonical_json(record) + "\n" for record in ordered), encoding="utf-8")
