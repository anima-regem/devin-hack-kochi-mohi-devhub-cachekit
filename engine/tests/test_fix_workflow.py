from pathlib import Path

import pytest
from cachekit.cli import app
from cachekit.fix.approve import approve
from cachekit.fix.content import check_content
from cachekit.fix.models import VerifyResult
from cachekit.fix.task import make_task, task_markdown
from cachekit.ingest.fix import changes, file_sha, snapshot, write_model
from cachekit.ingest.fix_workflow import load_bundle, verify_bundle
from cachekit.models import Message, RequestRecord
from fix_helpers import CANDIDATE, fake_quality, temporary_bundle
from typer.testing import CliRunner


def check(repo, bundle, report_path, tokenizer, quality=None, reviews=()):
    return verify_bundle(
        repo=repo,
        task_path=bundle / "fix_task.json",
        report_path=report_path,
        input_path=repo / "data/demo/inputs.jsonl",
        tokenizer=tokenizer,
        quality_path=quality,
        review_paths=list(reviews),
    )


def test_content_checks_text_tools_roles_settings_and_restored_history():
    before = RequestRecord(
        id="a",
        ts=0,
        model="fixture",
        tools=[{"name": "b"}, {"name": "a"}],
        messages=[
            Message(role="system", content="Dynamic value\nStatic policy"),
            Message(role="user", content="Question"),
        ],
        params={"temperature": 0},
    )
    after = before.model_copy(deep=True)
    after.messages[0].content = "Static policy\nDynamic value"
    after.tools.reverse()
    assert check_content([before], [after], []).passed
    dropped = after.model_copy(deep=True)
    dropped.messages[0].content = "Static policy"
    assert not check_content([before], [dropped], []).passed
    changed_tools = after.model_copy(update={"tools": []})
    assert not check_content([before], [changed_tools], []).passed
    changed_settings = after.model_copy(update={"params": {"temperature": 1}})
    assert not check_content([before], [changed_settings], []).passed
    changed_role = after.model_copy(deep=True)
    changed_role.messages[-1].role = "assistant"
    assert not check_content([before], [changed_role], []).passed
    history = [
        Message(role="user", content="Earlier fact"),
        Message(role="assistant", content="Noted"),
    ]
    restored = after.model_copy(deep=True)
    restored.messages[1:1] = history
    assert not check_content([before], [restored], []).passed
    result = check_content([before], [restored], [], {"a": history})
    assert result.passed and result.restored_history_lines == 2


def test_snapshot_identity_ignores_private_artifacts_and_catches_source_and_mode(tmp_path):
    (tmp_path / "source.py").write_text("original")
    (tmp_path / ".env").write_text("PRIVATE_SENTINEL")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/log.json").write_text("PRIVATE_LOG")
    first = snapshot(tmp_path)
    assert set(first.files) == {"source.py"}
    (tmp_path / ".env").write_text("CHANGED_PRIVATE")
    assert snapshot(tmp_path).sha256 == first.sha256
    (tmp_path / "source.py").write_text("modified")
    second = snapshot(tmp_path)
    paths, diff = changes(first, second)
    assert paths == ["source.py"] and diff != changes(first, first)[1]
    (tmp_path / "source.py").chmod(0o755)
    assert snapshot(tmp_path).sha256 != second.sha256


def test_tasks_do_not_export_report_preview_raw_evidence_or_route_names(
    tmp_path, config, qwen_tokenizer
):
    repo, bundle, baseline, report_path = temporary_bundle(tmp_path, qwen_tokenizer, config)
    from cachekit.fix.models import GenerationConfig
    from cachekit.ingest.fix import read_model
    from cachekit.models import Report

    report = read_model(report_path, Report)
    for finding in report.findings:
        finding.route = "PRIVATE_ROUTE"
        finding.evidence = ["PRIVATE_EVIDENCE"]
        finding.fix_hint = "PRIVATE_HINT"
        finding.code_locations = [{"content": "PRIVATE_LOCATION"}]
    report.template_preview = {"private": "PRIVATE_PROMPT"}
    task = make_task(
        report,
        report_sha256="a" * 64,
        before_source_sha256=baseline.source.sha256,
        golden_suite_sha256=baseline.task.golden_suite_sha256,
        allowed_files=baseline.task.allowed_files,
        test_command=baseline.task.test_command,
        generation=GenerationConfig(),
    )
    payload = task.model_dump_json() + task_markdown(task)
    assert "PRIVATE_" not in payload
    assert "Self-verification before" not in payload  # ranked stretch is not claimed implemented
    assert "source locations are not inferred" in payload
    assert task == make_task(
        report,
        report_sha256="a" * 64,
        before_source_sha256=baseline.source.sha256,
        golden_suite_sha256=baseline.task.golden_suite_sha256,
        allowed_files=baseline.task.allowed_files,
        test_command=baseline.task.test_command,
        generation=GenerationConfig(),
    )


def test_verify_candidate_needs_real_quality_artifact_before_approval(
    tmp_path, config, qwen_tokenizer
):
    repo, bundle, baseline, report_path = temporary_bundle(tmp_path, qwen_tokenizer, config)
    (repo / "demo_app/helpdesk/prompt.py").write_text(CANDIDATE)
    pending, _, _ = check(repo, bundle, report_path, qwen_tokenizer)
    assert pending.content_check.passed
    assert pending.prefix_check.passed
    assert pending.tests.status == "passed"
    assert not pending.passed and pending.quality_guard.status == "not_run"
    with pytest.raises(ValueError, match="all verification gates"):
        approve(
            pending,
            current_source_sha256=pending.after_source_sha256,
            expected_diff_sha256=pending.diff_sha256,
            verify_sha256="a" * 64,
            quality_result_sha256="b" * 64,
            reviewer="Unit test",
            timestamp="test",
        )
    quality = repo / "eval_results/quality.json"
    write_model(quality, fake_quality(repo, bundle, baseline, qwen_tokenizer))
    passed, _, _ = check(repo, bundle, report_path, qwen_tokenizer, quality)
    assert passed.passed
    approved = approve(
        passed,
        current_source_sha256=passed.after_source_sha256,
        expected_diff_sha256=passed.diff_sha256,
        verify_sha256="a" * 64,
        quality_result_sha256=file_sha(quality),
        reviewer="Unit test only",
        timestamp="test",
    )
    assert approved.diff_sha256 == passed.diff_sha256
    verification_path = repo / "eval_results/passing-fixture-verify.json"
    write_model(verification_path, passed)
    cli_approval = CliRunner().invoke(
        app,
        [
            "approve",
            "--verify",
            str(verification_path),
            "--baseline",
            str(report_path),
            "--inputs",
            str(repo / "data/demo/inputs.jsonl"),
            "--task",
            str(bundle / "fix_task.json"),
            "--repo",
            str(repo),
            "--tokenizer",
            str(Path(__file__).resolve().parents[2] / "data/tokenizer"),
            "--reviewer",
            "Unit test only",
            "--diff-sha256",
            passed.diff_sha256,
            "--out",
            str(repo / "eval_results/unit-test-approval.json"),
        ],
    )
    assert cli_approval.exit_code == 0, cli_approval.output
    with pytest.raises(ValueError, match="stale"):
        approve(
            passed,
            current_source_sha256="c" * 64,
            expected_diff_sha256=passed.diff_sha256,
            verify_sha256="a" * 64,
            quality_result_sha256=file_sha(quality),
            reviewer="Test",
            timestamp="test",
        )


def test_repository_test_failures_are_recorded_without_stdout(tmp_path):
    import sys

    from cachekit.ingest.fix import run_tests

    script = tmp_path / "failing_test.py"
    script.write_text("print('PRIVATE_TEST_OUTPUT')\nraise SystemExit(1)\n")
    result = run_tests(tmp_path, [sys.executable, str(script)])
    assert result.status == "failed" and result.exit_code == 1
    assert result.output_sha256 is not None
    assert "PRIVATE_TEST_OUTPUT" not in result.model_dump_json()


def test_replay_blocks_python_network_calls(tmp_path, config, qwen_tokenizer):
    from cachekit.ingest.fix import read_recorded, render_in_repo

    repo, bundle, baseline, report_path = temporary_bundle(tmp_path, qwen_tokenizer, config)
    path = repo / "demo_app/helpdesk/prompt.py"
    path.write_text(
        path.read_text().replace(
            "    if now.tzinfo is None",
            "    import socket\n    socket.create_connection(('example.com', 443))\n"
            "    if now.tzinfo is None",
        )
    )
    with pytest.raises(ValueError, match="output withheld"):
        render_in_repo(repo, read_recorded(repo / "data/demo/inputs.jsonl"))


def test_scope_and_signature_fail_before_executing_candidate(tmp_path, config, qwen_tokenizer):
    repo, bundle, baseline, report_path = temporary_bundle(tmp_path, qwen_tokenizer, config)
    (repo / "unexpected.py").write_text("unexpected = True")
    result, after, _ = check(repo, bundle, report_path, qwen_tokenizer)
    assert not result.scope_check.passed and not after and result.tests.status == "not_run"
    (repo / "unexpected.py").unlink()
    path = repo / "demo_app/helpdesk/prompt.py"
    path.write_text(
        path.read_text().replace("*, now: datetime", "*, forbidden: str, now: datetime")
    )
    result, after, _ = check(repo, bundle, report_path, qwen_tokenizer)
    assert not result.signature_check.passed and not after


def test_mutated_baseline_and_inputs_rejected(tmp_path, config, qwen_tokenizer):
    repo, bundle, baseline, report_path = temporary_bundle(tmp_path, qwen_tokenizer, config)
    (bundle / "before_requests.jsonl").write_text("modified")
    with pytest.raises(ValueError, match="checksum"):
        load_bundle(bundle / "fix_task.json")


def test_cli_unmodified_builder_remains_unapproved_and_devin_requires_permission(
    tmp_path, config, qwen_tokenizer
):
    repo, bundle, baseline, report_path = temporary_bundle(tmp_path, qwen_tokenizer, config)
    runner = CliRunner()
    out = repo / "eval_results/verify.json"
    result = runner.invoke(
        app,
        [
            "verify",
            "--repo",
            str(repo),
            "--task",
            str(bundle / "fix_task.json"),
            "--baseline",
            str(report_path),
            "--inputs",
            str(repo / "data/demo/inputs.jsonl"),
            "--tokenizer",
            str(Path(__file__).resolve().parents[2] / "data/tokenizer"),
            "--out",
            str(out),
            "--rendered-out",
            str(repo / "data/after.jsonl"),
        ],
    )
    assert result.exit_code == 1, result.output
    assert VerifyResult.model_validate_json(out.read_bytes()).quality_guard.status == "not_run"
    # This must fail before loading credentials or making an API request.
    result = runner.invoke(
        app, ["fix", str(bundle / "fix_task.json"), "--repo", str(repo), "--fixer", "devin"]
    )
    assert result.exit_code == 1 and "explicitly approve" in result.output
