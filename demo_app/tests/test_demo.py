"""Known synthetic cases for the six planted breakers and replay determinism."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest
from cachekit.models import Message, RequestRecord
from cachekit.serialization import canonical_json

from demo_app.helpdesk.before import POLICY_TEXT, build_request
from demo_app.helpdesk.catalog import EXAMPLES, QUESTIONS
from demo_app.helpdesk.models import HelpdeskInput, RecordedInput, RetrievedDocument, UserProfile
from demo_app.traffic import TrafficConfig, generate_inputs, render_inputs, write_traffic

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


def fixture_input() -> HelpdeskInput:
    return HelpdeskInput(
        user=UserProfile(id="synthetic-a", name="Alex"), message="Where is my order?"
    )


def system(inp: HelpdeskInput, *, seed: int = 42, now: datetime = NOW) -> str:
    return build_request(inp, now=now, rng=Random(seed))["messages"][0]["content"]


def test_timestamp_is_first_and_changes_before_handbook() -> None:
    inp = fixture_input()
    before = system(inp)
    assert before.startswith(f"Current time: {NOW.isoformat()}")
    assert before != system(inp, now=NOW + timedelta(seconds=1))
    assert before == system(inp)
    assert before.endswith(POLICY_TEXT)


def test_user_identity_changes_before_stable_policy_without_mutating_input() -> None:
    inp = fixture_input()
    snapshot = inp.model_dump()
    another = inp.model_copy(deep=True)
    another.user.name = "Morgan"
    first, second = system(inp), system(another)
    assert "Customer: Alex" in first and "Customer: Morgan" in second
    assert first.endswith(POLICY_TEXT) and second.endswith(POLICY_TEXT)
    assert inp.model_dump() == snapshot
    assert system(inp) == first


def test_seeded_few_shots_change_before_policy_but_repeat_for_the_same_seed() -> None:
    inp = fixture_input()
    first = system(inp, seed=1)
    assert first != system(inp, seed=2)
    assert first == system(inp, seed=1)
    assert first.index("Support examples") < first.index("Company support handbook")
    assert len(EXAMPLES) == 20
    assert len(set(QUESTIONS)) == len(QUESTIONS) == 300


def test_retrieved_content_precedes_policy_and_is_absent_when_not_supplied() -> None:
    inp = fixture_input()
    inp.retrieved_docs = [RetrievedDocument(id="doc-a", text="Fictional shipment note A")]
    rendered = system(inp)
    assert rendered.index("Fictional shipment note A") < rendered.index("Company support handbook")
    inp.retrieved_docs[0].text = "Fictional shipment note B"
    assert system(inp) != rendered
    inp.retrieved_docs = []
    assert "Fictional shipment note" not in system(inp)


def test_history_window_drops_only_the_oldest_messages_when_over_limit() -> None:
    inp = fixture_input()
    inp.history = [
        Message(role="user" if i % 2 == 0 else "assistant", content=f"turn-{i}") for i in range(10)
    ]
    request = build_request(inp, now=NOW, rng=Random(42))
    assert [message["content"] for message in request["messages"][1:-1]] == [
        f"turn-{i}" for i in range(4, 10)
    ]
    assert len(inp.history) == 10
    inp.history = inp.history[:6]
    retained = build_request(inp, now=NOW, rng=Random(42))
    assert [m["content"] for m in retained["messages"][1:-1]] == [f"turn-{i}" for i in range(6)]


def test_tools_vary_by_recorded_process_seed_and_replay_exactly() -> None:
    # Several hash seeds avoid depending on one particular pair's set permutation.
    records = [
        RecordedInput(
            id=f"tool-{seed}",
            ts=NOW.timestamp(),
            session_id="tools",
            input=fixture_input(),
            now=NOW,
            rng_seed=42,
            worker_seed=seed,
        )
        for seed in range(4)
    ]
    first = render_inputs(records, builder_version="before")
    second = render_inputs(records, builder_version="before")
    assert [canonical_json(record) for record in first] == [
        canonical_json(record) for record in second
    ]
    orders = [tuple(tool["function"]["name"] for tool in record.tools) for record in first]
    assert len(set(orders)) > 1
    assert all(set(order) == set(orders[0]) for order in orders)


def test_builder_rejects_an_unrecorded_naive_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_request(fixture_input(), now=NOW.replace(tzinfo=None), rng=Random(42))


def test_tool_definitions_are_not_shared_between_requests() -> None:
    inp = fixture_input()
    first = build_request(inp, now=NOW, rng=Random(42))
    first["tools"][0]["function"]["description"] = "mutated"
    second = build_request(inp, now=NOW, rng=Random(42))
    assert all(tool["function"]["description"] != "mutated" for tool in second["tools"])


def test_traffic_is_sorted_seeded_and_has_truncation_cases() -> None:
    config = TrafficConfig(users=2, min_turns=10, max_turns=10)
    first = generate_inputs(config)
    assert first == generate_inputs(config)
    assert [(r.ts, r.id) for r in first] == sorted((r.ts, r.id) for r in first)
    assert len({r.id for r in first}) == len(first)
    assert any(len(r.input.history) > 6 for r in first)
    assert first != generate_inputs(config.model_copy(update={"seed": 99}))


def test_serialized_inputs_rerender_to_byte_identical_requests(tmp_path: Path) -> None:
    manifest = write_traffic(TrafficConfig(users=2, min_turns=5, max_turns=5), tmp_path)
    recorded = [
        RecordedInput.model_validate_json(line)
        for line in (tmp_path / "inputs.jsonl").read_text().splitlines()
    ]
    rerendered = "".join(
        canonical_json(record) + "\n"
        for record in render_inputs(recorded, builder_version="before")
    )
    assert rerendered.encode() == (tmp_path / "requests_before.jsonl").read_bytes()
    assert manifest.n_requests == len(recorded)
    assert all(
        RequestRecord.model_validate_json(line).provider == "vllm"
        for line in rerendered.splitlines()
    )


def test_empty_render_and_invalid_turn_bounds() -> None:
    assert render_inputs([]) == []
    with pytest.raises(ValueError, match="min_turns"):
        generate_inputs(TrafficConfig(min_turns=8, max_turns=2))
