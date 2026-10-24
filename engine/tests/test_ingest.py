import hashlib
import json
from pathlib import Path
from random import Random

import pytest
from cachekit.ingest.glaive import GlaiveConfig, GlaiveRow, convert_glaive, extract_tools
from cachekit.ingest.jsonl import read_requests, write_requests
from cachekit.ingest.swe_agent import ArrivalConfig, Trajectory, convert_trajectory
from cachekit.models import RequestRecord


def test_native_roundtrip_hash_and_safe_errors(tmp_path: Path) -> None:
    path = tmp_path / "requests.jsonl"
    record = RequestRecord(id="a", ts=0, messages=[{"role": "user", "content": "PRIVATE"}])
    write_requests([record], path)
    records, digest = read_requests(path)
    assert records == [record]
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text('{"messages": "PRIVATE"}\n')
    with pytest.raises(ValueError) as error:
        read_requests(path)
    assert "PRIVATE" not in str(error.value)
    write_requests([record, record], path)
    with pytest.raises(ValueError, match="Duplicate"):
        read_requests(path)


def test_swe_emits_context_before_each_model_call_not_its_own_answer() -> None:
    row = Trajectory.model_validate(
        {
            "instance_id": "synthetic-1",
            "model_name": "fixture",
            "trajectory": [
                {"role": "system", "system_prompt": "POLICY"},
                {"role": "user", "text": "question"},
                {"role": "ai", "text": "first answer"},
                {"role": "user", "text": "observation"},
                {"role": "ai", "text": "second answer"},
            ],
        }
    )
    timing = ArrivalConfig(seed=7)
    first = convert_trajectory(row, index=0, arrival=0, rng=Random(7), timing=timing)
    assert len(first) == 2
    assert [m.content for m in first[0].messages] == ["POLICY", "question"]
    assert first[1].messages[-1].content == "observation"
    assert first[1].ts > first[0].ts
    assert first == convert_trajectory(row, index=0, arrival=0, rng=Random(7), timing=timing)


def test_glaive_extracts_multiple_tools_and_preserves_observations() -> None:
    function = {"name": "a", "parameters": {"type": "object", "properties": {}}}
    another = function | {"name": "b"}
    raw = "SYSTEM: Use tools: " + json.dumps(function) + "\n" + json.dumps(another)
    _, tools = extract_tools(raw)
    assert len(tools) == 2
    row = GlaiveRow(
        system=raw,
        chat=(
            "USER: first\n\nASSISTANT: <functioncall> {}<|endoftext|>\n\n"
            "FUNCTION RESPONSE: observed\n\nASSISTANT: final<|endoftext|>"
        ),
    )
    records = convert_glaive(row, index=0, config=GlaiveConfig(seed=7))
    assert len(records) == 2
    assert records[1].messages[-1].content == "observed"
    assert "functioncall" in records[1].messages[-2].content
    assert records[0].tools == tools
    assert convert_glaive(row, index=0, config=GlaiveConfig(seed=7)) == records


def test_glaive_no_tools_and_no_implicit_planting() -> None:
    row = GlaiveRow(system="SYSTEM: Be helpful.", chat="USER: hello\nASSISTANT: hi")
    records = convert_glaive(row, index=0, config=GlaiveConfig(seed=1))
    assert records[0].tools is None
    assert records[0].meta["planted"] == []
    with pytest.raises(ValueError, match="markers"):
        convert_glaive(GlaiveRow(system="x", chat="PRIVATE"), index=0, config=GlaiveConfig(seed=1))
