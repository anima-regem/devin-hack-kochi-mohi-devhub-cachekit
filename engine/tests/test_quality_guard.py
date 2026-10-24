import json

import httpx
import pytest
from cachekit.fix.models import GoldenSuite, QualityReview
from cachekit.fix.quality import evaluate_quality, parse_tool_calls, validate_suite
from cachekit.fix.task import digest
from cachekit.ingest.config import load_config
from cachekit.ingest.fix import read_model, render_in_repo
from cachekit.ingest.fix_workflow import _golden_records
from cachekit.ingest.jsonl import read_requests
from fix_helpers import CANDIDATE, fake_quality, temporary_bundle

from bench.quality import collect_quality, validate_endpoint


@pytest.fixture(scope="module")
def prepared(tmp_path_factory, qwen_tokenizer):
    repo, bundle, baseline, _ = temporary_bundle(
        tmp_path_factory.mktemp("quality"), qwen_tokenizer, load_config()
    )
    (repo / "demo_app/helpdesk/prompt.py").write_text(CANDIDATE)
    suite = read_model(bundle / "golden_suite.json", GoldenSuite)
    before, _ = read_requests(bundle / "golden_before.jsonl")
    after = render_in_repo(repo, _golden_records(suite))
    run = fake_quality(repo, bundle, baseline, qwen_tokenizer)
    return repo, bundle, baseline, suite, before, after, run, qwen_tokenizer


def evaluate(prepared, run, reviews=()):
    repo, bundle, baseline, suite, before, after, original, tokenizer = prepared
    return evaluate_quality(
        run,
        task=baseline.task,
        after_source_sha256=original.after_source_sha256,
        diff_sha256=original.diff_sha256,
        suite=suite,
        before=before,
        after=after,
        tokenizer=tokenizer,
        config=baseline.config,
        result_sha256="a" * 64,
        reviews=list(reviews),
    )


def test_quality_absence_fails_closed_and_fake_known_answers_are_recomputed(prepared):
    run = prepared[-2]
    assert evaluate(prepared, None).status == "not_run"
    result = evaluate(prepared, run)
    assert result.status == "passed"
    assert len(result.cases) == 5 and all(c.exact_match for c in result.cases)
    bad = run.model_copy(deep=True)
    for output in bad.outputs:
        if output.id == "golden-continuity":
            output.before.text = output.after.text = "unknown"
    # Identical wrong answers are not a quality pass.
    assert evaluate(prepared, bad).status == "failed"


@pytest.mark.parametrize(
    "field",
    [
        "task_sha256",
        "before_source_sha256",
        "after_source_sha256",
        "diff_sha256",
        "golden_suite_sha256",
        "config_sha256",
    ],
)
def test_changed_evidence_identity_is_stale(prepared, field):
    bad = prepared[-2].model_copy(deep=True)
    setattr(bad, field, "f" * 64)
    assert evaluate(prepared, bad).status == "stale"


def test_changed_parameters_revision_prompt_and_case_coverage_are_stale(prepared):
    for mutate in [
        lambda r: setattr(r.generation, "seed", 99),
        lambda r: setattr(r.deployment, "revision", "wrong-revision"),
        lambda r: setattr(r.outputs[0], "after_prompt_sha256", "f" * 64),
        lambda r: setattr(r.outputs[0].after, "prompt_tokens", 1),
        lambda r: setattr(r.outputs[0], "id", r.outputs[1].id),
        lambda r: r.tokenizer_identity.update(mode="approximate"),
    ]:
        bad = prepared[-2].model_copy(deep=True)
        mutate(bad)
        assert evaluate(prepared, bad).status == "stale"


def test_changed_outputs_need_exact_artifact_bound_human_review(prepared):
    run = prepared[-2].model_copy(deep=True)
    output = next(o for o in run.outputs if o.id == "golden-continuity")
    output.after.text = "The color was cobalt."
    assert evaluate(prepared, run).status == "review_required"
    review = QualityReview(
        quality_result_sha256="a" * 64,
        case_id=output.id,
        before_output_sha256=digest(output.before),
        after_output_sha256=digest(output.after),
        reviewer="Unit test",
        reason="Different wording preserves the asserted fact.",
        timestamp="test",
    )
    assert evaluate(prepared, run, [review]).status == "passed"
    review.quality_result_sha256 = "b" * 64
    assert evaluate(prepared, run, [review]).status == "review_required"


def test_review_never_overrides_failed_assertion_or_truncation(prepared):
    run = prepared[-2].model_copy(deep=True)
    output = next(o for o in run.outputs if o.id == "golden-continuity")
    output.after.text = "unknown"
    review = QualityReview(
        quality_result_sha256="a" * 64,
        case_id=output.id,
        before_output_sha256=digest(output.before),
        after_output_sha256=digest(output.after),
        reviewer="Unit test",
        reason="Cannot waive a failed assertion",
        timestamp="test",
    )
    assert evaluate(prepared, run, [review]).status == "failed"
    run = prepared[-2].model_copy(deep=True)
    run.outputs[0].after.finish_reason = "length"
    assert evaluate(prepared, run).status == "failed"


def test_json_schema_and_actual_tool_call_check_cannot_be_bypassed(prepared):
    run = prepared[-2].model_copy(deep=True)
    output = next(o for o in run.outputs if o.id == "golden-time")
    output.after.text = '{"date":"2026-10-24","extra":true}'
    result = evaluate(prepared, run)
    assert result.status == "failed"
    assert next(c for c in result.cases if c.id == output.id).json_after_valid is False
    run = prepared[-2].model_copy(deep=True)
    output = next(o for o in run.outputs if o.id == "golden-authorization")
    output.after.text = (
        'confirm item <tool_call>{"name":"create_return","arguments":{}}</tool_call>'
    )
    output.after.tool_calls = []  # forged collector claim must be rejected
    assert evaluate(prepared, run).status == "failed"
    output.after.tool_calls = parse_tool_calls(output.after.text)
    assert evaluate(prepared, run).status == "failed"
    with pytest.raises(ValueError, match="Incomplete"):
        parse_tool_calls("<tool_call>{}")


def test_suite_rejects_external_json_schema_resolution(prepared):
    suite = prepared[3].model_copy(deep=True)
    suite.cases[0].output_json_schema = {"$ref": "https://example.com/schema"}
    with pytest.raises(ValueError, match="external"):
        validate_suite(suite)


def test_versioned_public_suite_matches_declared_case_generator():
    from pathlib import Path

    from demo_app.goldens import suite

    path = Path(__file__).resolve().parents[2] / "demo_app/goldens.json"
    assert read_model(path, GoldenSuite) == suite()


def test_collector_posts_only_fixed_synthetic_token_ids_to_vllm(prepared):
    repo, bundle, baseline, suite, before, after, run, tokenizer = prepared
    calls = []
    sorted_cases = sorted(run.outputs, key=lambda o: o.id)

    def handler(request):
        calls.append(request)
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": run.deployment.vllm_version})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": run.deployment.model}]})
        payload = json.loads(request.content)
        index = sum(r.method == "POST" for r in calls) - 1
        text = sorted_cases[index // 2].before.text
        assert payload["temperature"] == 0 and payload["seed"] == 42
        assert isinstance(payload["prompt"], list) and "messages" not in payload
        return httpx.Response(
            200,
            json={
                "model": run.deployment.model,
                "choices": [{"text": text, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": len(payload["prompt"]), "completion_tokens": 8},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = collect_quality(
            repo=repo,
            task_path=bundle / "fix_task.json",
            endpoint="http://127.0.0.1:8000",
            deployment=run.deployment,
            tokenizer=tokenizer,
            client=client,
        )
    assert len(result.outputs) == 5 and sum(r.method == "POST" for r in calls) == 10
    assert evaluate(prepared, result).status == "passed"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com",
        "https://api.devin.ai",
        "http://external.example",
        "https://example.modal.run.evil.test",
        "https://user:password@example.modal.run",
        "https://example.modal.run/v1?secret=x",
    ],
)
def test_collector_rejects_external_or_ambiguous_endpoints(url):
    with pytest.raises(ValueError, match="local vLLM"):
        validate_endpoint(url)
