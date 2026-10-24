"""Temporary test-only candidates and fake inference; never saved as evaluation results."""

import shutil
import sys
from pathlib import Path

from cachekit.fix.models import (
    DeploymentIdentity,
    Generation,
    GenerationConfig,
    GoldenOutputs,
    QualityRun,
)
from cachekit.fix.quality import prompt_identity
from cachekit.fix.task import digest, task_markdown
from cachekit.ingest.fix import changes, read_model, render_in_repo, snapshot, write_model
from cachekit.ingest.fix_workflow import _golden_records, prepare_task
from cachekit.ingest.jsonl import read_requests
from cachekit.render.tokenize import tokenize
from cachekit.report import analyze

from demo_app.goldens import suite
from demo_app.traffic import TrafficConfig, write_traffic

REPO = Path(__file__).resolve().parents[2]

# This fixture is intentionally confined to temporary test repos. It is not the app's AFTER fix.
CANDIDATE = """from datetime import datetime
from random import Random
from cachekit.models import JsonObject
from demo_app.helpdesk.models import HelpdeskInput
from demo_app.helpdesk.before import build_request as before_build_request, POLICY_TEXT

def build_request(inp: HelpdeskInput, *, now: datetime, rng: Random) -> JsonObject:
    request = before_build_request(inp, now=now, rng=rng)
    system = request["messages"][0]["content"]
    head, marker, policy = system.partition("Company support handbook\\n")
    request["messages"][0]["content"] = marker + policy + "\\n" + head
    request["tools"].sort(key=lambda t: t["function"]["name"])
    request["messages"] = [request["messages"][0],
        *[m.model_dump(exclude_none=True) for m in inp.history],
        request["messages"][-1]]
    return request
"""


def temporary_bundle(tmp_path, tokenizer, config):
    repo = tmp_path / "repo"
    repo.mkdir()
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "demo_app", repo / "demo_app", ignore=ignored)
    shutil.copytree(REPO / "engine/cachekit", repo / "engine/cachekit", ignore=ignored)
    (repo / "fixture_tests.py").write_text("""from datetime import UTC, datetime
from random import Random
from demo_app.helpdesk.prompt import build_request
from demo_app.helpdesk.models import HelpdeskInput, UserProfile, ChatRequest
def test_public_request_contract():
    inp=HelpdeskInput(user=UserProfile(id="fixture",name="Fixture"),message="Check my order")
    req=ChatRequest.model_validate(build_request(inp,now=datetime(2026,10,24,tzinfo=UTC),rng=Random(42)))
    assert req.model == "Qwen/Qwen3-4B-Instruct-2507"
    assert req.temperature == 0 and req.max_tokens == 64
    assert {t["function"]["name"] for t in req.tools} == {"lookup_order", "track_shipment",
        "check_return", "create_return", "search_policy", "escalate_ticket"}
    assert req.messages[-1].content == "Check my order"
""")
    data = repo / "data/demo"
    write_traffic(TrafficConfig(users=2, min_turns=3, max_turns=3), data)
    records, input_hash = read_requests(data / "requests_before.jsonl")
    report = analyze(records, config, tokenizer, input_sha256=input_hash)
    report_path = repo / "eval_results/before.json"
    write_model(report_path, report)
    suite_path = repo / "demo_app/goldens.json"
    write_model(suite_path, suite())
    bundle = repo / "data/fixes/demo"
    baseline = prepare_task(
        repo=repo,
        report_path=report_path,
        input_path=data / "inputs.jsonl",
        before_path=data / "requests_before.jsonl",
        suite_path=suite_path,
        bundle=bundle,
        config=config,
        tokenizer=tokenizer,
        allowed_files=["demo_app/helpdesk/prompt.py"],
        finding_ids=None,
        test_command=[sys.executable, "-m", "pytest", "-q", "fixture_tests.py"],
        generation=GenerationConfig(),
    )
    write_model(bundle / "fix_task.json", baseline.task)
    write_model(bundle / "fix_baseline.json", baseline)
    (bundle / "fix_task.md").write_text(task_markdown(baseline.task))
    return repo, bundle, baseline, report_path


def fake_quality(repo, bundle, baseline, tokenizer):
    from cachekit.fix.models import GoldenSuite

    golden_suite = read_model(bundle / "golden_suite.json", GoldenSuite)
    before, _ = read_requests(bundle / "golden_before.jsonl")
    after = render_in_repo(repo, _golden_records(golden_suite))
    old, new = {r.id: r for r in before}, {r.id: r for r in after}
    texts = {
        "golden-time": '{"date":"2026-10-24","within_window":false}',
        "golden-locale": "Quel est le numéro de votre commande pour vérifier la livraison ?",
        "golden-authorization": "Please confirm the item and reason before creating a return.",
        "golden-retrieval": "RETRIEVAL-SYN-582",
        "golden-continuity": "cobalt",
    }
    outputs = []
    for case in golden_suite.cases:

        def output(request, text=texts[case.id]):
            return Generation(
                text=text,
                finish_reason="stop",
                prompt_tokens=len(tokenize(request, tokenizer).token_ids),
                completion_tokens=8,
            )

        outputs.append(
            GoldenOutputs(
                id=case.id,
                before=output(old[case.id]),
                after=output(new[case.id]),
                before_prompt_sha256=prompt_identity(old[case.id], tokenizer),
                after_prompt_sha256=prompt_identity(new[case.id], tokenizer),
            )
        )
    current = snapshot(repo, baseline.excluded_artifacts)
    _, diff_hash = changes(baseline.source, current)
    c = baseline.config.vllm
    return QualityRun(
        timestamp="2026-10-24T15:00:00+00:00",
        git_sha=None,
        task_sha256=digest(baseline.task),
        before_source_sha256=baseline.source.sha256,
        after_source_sha256=current.sha256,
        diff_sha256=diff_hash,
        golden_suite_sha256=digest(golden_suite),
        config_sha256=baseline.task.config_sha256,
        tokenizer_identity=tokenizer.identity,
        generation=baseline.task.quality_generation,
        deployment=DeploymentIdentity(
            model=c.model,
            revision=c.revision,
            tokenizer_revision=c.revision,
            vllm_version=c.version,
            gpu="L4",
            max_model_len=c.max_model_len,
            block_size=c.block_size,
            capacity_blocks=c.capacity_blocks,
            deployment_id="unit-test-fake-not-measured",
        ),
        outputs=outputs,
        note="FAKE inference fixture confined to a unit-test temporary directory.",
    )
