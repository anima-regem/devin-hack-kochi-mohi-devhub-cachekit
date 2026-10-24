"""Local Glaive parsing. Preserve text rather than inventing missing tool messages."""

import hashlib
import json
import re
from pathlib import Path
from random import Random

from pydantic import Field

from cachekit.models import BoundaryModel, JsonObject, Message, RequestRecord


class GlaiveRow(BoundaryModel):
    system: str
    chat: str


class GlaiveConfig(BoundaryModel):
    seed: int = Field(ge=0)
    tool_order_fraction: float = Field(default=0, ge=0, le=1)


def extract_tools(system: str) -> tuple[str, list[JsonObject]]:
    decoder = json.JSONDecoder()
    tools: list[JsonObject] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(system):
        start = system.find("{", cursor)
        if start < 0:
            break
        try:
            value, length = decoder.raw_decode(system[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        cursor = start + length
        if isinstance(value, dict) and isinstance(value.get("name"), str) and "parameters" in value:
            tools.append({"type": "function", "function": value})
            spans.append((start, cursor))
    text = system
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    return text.removeprefix("SYSTEM:").strip(), tools


def convert_glaive(row: GlaiveRow, *, index: int, config: GlaiveConfig) -> list[RequestRecord]:
    system, tools = extract_tools(row.system)
    rng = Random(config.seed + index)
    planted = bool(tools and len(tools) > 1 and rng.random() < config.tool_order_fraction)
    if planted:
        original = list(tools)
        rng.shuffle(tools)
        planted = tools != original
    messages = [Message(role="system", content=system)]
    result: list[RequestRecord] = []
    identity = hashlib.sha256(f"{index}:{row.system}:{row.chat}".encode()).hexdigest()[:16]
    # Markers are anchored to line starts to avoid interpreting a mention inside prose.
    marker = re.compile(r"(?m)^(USER|ASSISTANT|FUNCTION RESPONSE):\s*")
    matches = list(marker.finditer(row.chat))
    if not matches:
        raise ValueError("No Glaive conversation markers found; input content withheld")
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(row.chat)
        content = row.chat[match.end() : end].strip().removesuffix("<|endoftext|>").strip()
        if match[1] == "ASSISTANT":
            result.append(
                RequestRecord(
                    id=f"glaive-{identity}-{len(result):03d}",
                    ts=float(index * 1000 + position),
                    session_id=f"glaive-{identity}",
                    route="glaive.function-calling",
                    tools=tools or None,
                    messages=[message.model_copy(deep=True) for message in messages],
                    meta={
                        "source": "glaiveai/glaive-function-calling-v2",
                        "seed": config.seed,
                        "synthetic_arrivals": True,
                        "planted": ["tool_order"] if planted else [],
                        "function_calls_preserved_as_text": True,
                    },
                )
            )
            messages.append(Message(role="assistant", content=content))
        else:
            # Preserve function results as a user observation; no tool_call_id is invented.
            messages.append(Message(role="user", content=content))
    return result


def read_glaive(
    path: Path, *, limit: int, seed: int, tool_order_fraction: float = 0
) -> list[RequestRecord]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Glaive input must be a JSON array")
    config = GlaiveConfig(seed=seed, tool_order_fraction=tool_order_fraction)
    result: list[RequestRecord] = []
    for index, raw in enumerate(rows[:limit]):
        result.extend(convert_glaive(GlaiveRow.model_validate(raw), index=index, config=config))
    return sorted(result, key=lambda record: (record.ts, record.id))
