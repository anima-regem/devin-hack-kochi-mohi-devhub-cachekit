"""Offline integration against the real pinned model tokenizer, without weights."""

import hashlib
import socket
from pathlib import Path

import pytest
from cachekit.ingest.tokenizer import load_tokenizer
from cachekit.models import Message, RequestRecord
from cachekit.render.canonical import model_messages
from cachekit.render.tokenize import tokenize
from cachekit.report import _templates, analyze
from cachekit.serialization import canonical_json
from cachekit.simulate.rewrite import rewrite

from demo_app.helpdesk.prompt import POLICY_TEXT
from demo_app.traffic import TrafficConfig, generate_inputs, render_inputs


@pytest.fixture(scope="module")
def demo_requests():
    # Exceeds sample_limit and includes the actual multi-process tool-order defect.
    return render_inputs(
        generate_inputs(TrafficConfig(users=12, seed=42)), builder_version="before"
    )


def test_full_qwen_chat_template_not_segment_token_sums(qwen_tokenizer):
    record = RequestRecord(
        id="fixture",
        ts=0,
        system="Keep every symbol: café 👋",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Look up a record",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        messages=[Message(role="user", content="Check this order.")],
    )
    result = tokenize(record, qwen_tokenizer)
    direct = qwen_tokenizer.tokenizer.apply_chat_template(
        [m.model_dump(exclude_none=True) for m in model_messages(record)],
        tools=record.tools,
        tokenize=True,
        add_generation_prompt=True,
    )
    assert result.token_ids == direct
    assert len(result.offsets) == len(direct)
    assert qwen_tokenizer.tokenizer.decode(direct) == result.text


def test_demo_detects_six_without_ground_truth_and_is_offline(
    demo_requests,
    config,
    qwen_tokenizer,
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("The deterministic engine attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    records = [r.model_copy(deep=True) for r in demo_requests]
    for record in records:
        record.meta.clear()
    payload = canonical_json([r.model_dump(mode="json") for r in records])
    digest = hashlib.sha256(payload.encode()).hexdigest()
    report = analyze(records, config, qwen_tokenizer, input_sha256=digest)
    assert {f.breaker for f in report.findings} == {
        "timestamp",
        "user_identity",
        "tool_order",
        "few_shot_sampling",
        "rag_before_static",
        "history_truncation",
    }
    assert report.backends[0].achievable_hit_rate > report.backends[0].actual_hit_rate
    assert all(len(row) <= 2000 for row in report.heatmaps.values())
    assert canonical_json(report) == canonical_json(
        analyze(list(reversed(records)), config, qwen_tokenizer, input_sha256=digest)
    )
    assert payload == canonical_json([r.model_dump(mode="json") for r in records])


def test_simulated_movement_keeps_source_spans_and_static_policy(
    demo_requests,
    config,
    qwen_tokenizer,
):
    templates = _templates(demo_requests, config.analysis)
    # Classification is sufficient here; analysis additionally disables low-impact moves.
    for record in demo_requests:
        projected = rewrite(record, templates, sort_tools=True)
        rendered = qwen_tokenizer.render(projected)
        assert POLICY_TEXT in rendered
        for template in templates:
            for span in template.spans:
                if span.safe_to_move and span.label not in {
                    "json_key_order",
                    "whitespace_template",
                }:
                    value = span.values.get(record.id)
                    if value:
                        assert value in rendered


def test_clean_real_tokenizer_has_no_findings(config, qwen_tokenizer):
    items = [
        RequestRecord(
            id=str(i),
            ts=i,
            route="clean",
            system=POLICY_TEXT,
            messages=[Message(role="user", content=f"Question {i}")],
        )
        for i in range(3)
    ]
    report = analyze(items, config, qwen_tokenizer, input_sha256="a" * 64)
    assert not report.findings
    assert report.backends[0].actual_hit_rate == report.backends[0].achievable_hit_rate


def test_rendered_model_namespace_is_not_the_dataset_source_model(qwen_tokenizer):
    item = RequestRecord(
        id="fixture",
        ts=0,
        model="original-dataset-model",
        messages=[Message(role="user", content="hello")],
    )
    original = tokenize(item, qwen_tokenizer)
    item.model = qwen_tokenizer.identity["model"]
    assert tokenize(item, qwen_tokenizer).namespace == original.namespace
    item.params["cache_salt"] = "another-tenant"
    assert tokenize(item, qwen_tokenizer).namespace != original.namespace


def test_handbook_fits_documented_static_token_budget(qwen_tokenizer):
    tokens, _ = qwen_tokenizer.encode_offsets(POLICY_TEXT)
    assert 4000 <= len(tokens) <= 6000


def test_tokenizer_load_rejects_tampered_files(tmp_path, config):
    # Fail before transformers sees untrusted or inconsistent bytes.
    metadata = tmp_path / ".cache" / "huggingface" / "download"
    metadata.mkdir(parents=True)
    for name in ("tokenizer.json", "tokenizer_config.json", "config.json"):
        (tmp_path / name).write_text("{}")
        (metadata / f"{name}.metadata").write_text(config.vllm.revision + "\n" + "0" * 64 + "\n")
    with pytest.raises(ValueError, match="checksum"):
        load_tokenizer(tmp_path, model=config.vllm.model, revision=config.vllm.revision)


def test_exact_tokenizer_loading_cannot_use_network(config, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tokenizer loading attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    path = Path(__file__).resolve().parents[2] / "data" / "tokenizer"
    if not path.is_dir():
        pytest.skip("Pinned local tokenizer not present")
    loaded = load_tokenizer(path, model=config.vllm.model, revision=config.vllm.revision)
    assert loaded.identity["revision"] == config.vllm.revision
