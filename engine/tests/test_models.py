"""Boundary checks that protect future ingest, simulator, and UI integrations."""

import json
import math

import pytest
from cachekit.api import app as api
from cachekit.cli import app as cli
from cachekit.models import BackendResult, Hole, Report, RequestRecord
from cachekit.serialization import canonical_json
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner


def request(**changes: object) -> RequestRecord:
    fields = {"id": "r-1", "ts": 0.0, "messages": [{"role": "user", "content": "hello"}]}
    fields.update(changes)
    return RequestRecord.model_validate(fields)


def test_json_round_trip_preserves_tool_order_and_message_content() -> None:
    record = request(tools=[{"name": "z"}, {"name": "a"}])
    text = canonical_json(record)
    assert RequestRecord.model_validate_json(text) == record
    assert json.loads(text)["tools"] == [{"name": "z"}, {"name": "a"}]
    assert text == canonical_json(record)


def test_mutable_defaults_are_not_shared() -> None:
    first, second = request(), request()
    first.meta["source"] = "changed"
    assert second.meta == {}


@pytest.mark.parametrize("timestamp", [math.inf, -math.inf, math.nan])
def test_nonfinite_arrival_times_are_rejected(timestamp: float) -> None:
    with pytest.raises(ValidationError):
        request(ts=timestamp)


@pytest.mark.parametrize(
    "fields",
    [
        {"messages": []},
        {"messages": [{"role": "invented", "content": "x"}]},
        {"unexpected_field": True},
    ],
)
def test_bad_request_boundaries_are_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        request(**fields)


def test_hole_span_and_redacted_sample_bounds() -> None:
    fields = dict(
        segment_kind="system",
        segment_index=0,
        char_start=2,
        char_end=4,
        cardinality=2,
        sample_values=["<redacted>"],
        label="timestamp",
    )
    assert Hole(**fields).char_end == 4
    with pytest.raises(ValidationError):
        Hole(**(fields | {"char_end": 1}))
    with pytest.raises(ValidationError):
        Hole(**(fields | {"sample_values": ["redacted"] * 4}))


def test_cache_rates_must_be_fractions() -> None:
    with pytest.raises(ValidationError):
        BackendResult(
            backend="vllm",
            params={},
            actual_hit_rate=1.1,
            achievable_hit_rate=0,
            tokens_recomputed_actual=0,
            tokens_recomputed_achievable=0,
        )


def test_report_rejects_invalid_stability_and_oversized_heatmaps() -> None:
    fields = dict(
        version="0.1.0",
        input_sha256="a" * 64,
        config_sha256="b" * 64,
        n_requests=0,
        routes=[],
        backends=[],
        findings=[],
        heatmaps={},
        template_preview={},
    )
    assert Report(**fields).n_requests == 0
    for heatmap in [[-0.1], [1.1], [0.5] * 2001]:
        with pytest.raises(ValidationError):
            Report(**(fields | {"heatmaps": {"route": heatmap}}))


def test_canonical_serialization_removes_mapping_insertion_order() -> None:
    assert canonical_json({"b": {"y": 1, "x": 2}, "a": "é"}) == canonical_json(
        {"a": "é", "b": {"x": 2, "y": 1}}
    )
    with pytest.raises(ValueError):
        canonical_json({"bad": math.nan})


def test_cli_exports_parseable_contract_and_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--model", "RequestRecord"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["title"] == "RequestRecord"
    version = runner.invoke(cli, ["--version"])
    assert version.exit_code == 0
    assert version.output.strip() == "cachekit 0.1.0"


def test_api_health_has_no_analysis_claim() -> None:
    response = TestClient(api).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
