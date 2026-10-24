"""Local orchestration around pure task, content, simulation and quality checks."""

import hashlib
from pathlib import Path

from cachekit.fix.content import check_content
from cachekit.fix.models import (
    FixBaseline,
    FixTask,
    GenerationConfig,
    GoldenSuite,
    QualityReview,
    QualityRun,
    QualityStatus,
    TestResult,
)
from cachekit.fix.quality import evaluate_quality, validate_suite
from cachekit.fix.task import digest, make_task
from cachekit.fix.verify import assemble_verification
from cachekit.ingest.fix import (
    builder_signature,
    changes,
    file_sha,
    read_model,
    read_recorded,
    render_in_repo,
    run_tests,
    snapshot,
    write_model,
)
from cachekit.ingest.jsonl import read_requests, write_requests
from cachekit.models import Message, Report
from cachekit.report import _templates, analyze
from cachekit.serialization import canonical_json
from cachekit.settings import RunConfig

BUNDLE_NAMES = (
    "fix_task.md",
    "fix_task.json",
    "fix_baseline.json",
    "recorded_inputs.jsonl",
    "before_requests.jsonl",
    "golden_suite.json",
    "golden_before.jsonl",
)


def _golden_records(suite: GoldenSuite) -> list[dict]:
    from demo_app.helpdesk.models import RecordedInput

    result = []
    for case in suite.cases:
        record = RecordedInput.model_validate(case.recorded_input)
        if record.id != case.id:
            raise ValueError("Golden case ID and recorded input ID must match")
        result.append(record.model_dump(mode="json"))
    return result


def prepare_task(
    *,
    repo: Path,
    report_path: Path,
    input_path: Path,
    before_path: Path,
    suite_path: Path,
    bundle: Path,
    config: RunConfig,
    tokenizer,
    allowed_files: list[str],
    test_command: list[str],
    finding_ids: list[str] | None,
    generation: GenerationConfig,
) -> FixBaseline:
    if not bundle.resolve().is_relative_to(repo.resolve() / "data"):
        raise ValueError(
            "Keep local baseline bundles under the repository's gitignored data/ directory"
        )
    if any((bundle / name).exists() for name in BUNDLE_NAMES):
        raise ValueError(
            "Task bundle already exists; create a new directory to preserve its baseline"
        )
    exclusions = []
    for name in BUNDLE_NAMES:
        path = (bundle / name).resolve()
        if path.is_relative_to(repo.resolve()):
            exclusions.append(path.relative_to(repo.resolve()).as_posix())
    before_source = snapshot(repo, exclusions)
    report = read_model(report_path, Report)
    before, input_hash = read_requests(before_path)
    if input_hash != report.input_sha256:
        raise ValueError("BEFORE request checksum does not match the supplied report")
    if report.config_sha256 != digest(
        {"config": config.model_dump(mode="json"), "tokenizer": tokenizer.identity}
    ):
        raise ValueError("Analysis configuration/tokenizer no longer matches the report")
    records = read_recorded(input_path)
    rendered = render_in_repo(repo, records)

    # Old log metadata need not name the current worker version; actual requests must match.
    def contract(items):
        return [
            r.model_dump(mode="json", exclude={"meta"}) for r in sorted(items, key=lambda r: r.id)
        ]

    if contract(before) != contract(rendered):
        raise ValueError("Current builder does not reproduce the BEFORE requests on these inputs")
    suite = read_model(suite_path, GoldenSuite)
    validate_suite(suite)
    golden_before = render_in_repo(repo, _golden_records(suite))
    task = make_task(
        report,
        report_sha256=file_sha(report_path),
        before_source_sha256=before_source.sha256,
        golden_suite_sha256=digest(suite),
        allowed_files=allowed_files,
        test_command=test_command,
        finding_ids=finding_ids,
        generation=generation,
    )
    if any(path not in before_source.files for path in task.allowed_files):
        raise ValueError("Every allowed file must exist in the audited source snapshot")
    if set(task.allowed_files).intersection(exclusions):
        raise ValueError("A fix source file cannot also be an excluded artifact")
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "recorded_inputs.jsonl").write_bytes(input_path.read_bytes())
    (bundle / "before_requests.jsonl").write_bytes(before_path.read_bytes())
    write_requests(golden_before, bundle / "golden_before.jsonl")
    write_model(bundle / "golden_suite.json", suite)
    baseline = FixBaseline(
        task=task,
        source=before_source,
        recorded_inputs_sha256=file_sha(input_path),
        before_requests_sha256=input_hash,
        golden_before_sha256=file_sha(bundle / "golden_before.jsonl"),
        builder_signature_sha256=builder_signature(repo),
        config=config,
        tokenizer_identity=tokenizer.identity,
        baseline_hit_rate=next(b.actual_hit_rate for b in report.backends if b.backend == "vllm"),
        excluded_artifacts=exclusions,
    )
    if snapshot(repo, exclusions).sha256 != before_source.sha256:
        raise ValueError("Source changed while preparing the baseline")
    return baseline


def load_bundle(task_path: Path) -> tuple[FixBaseline, GoldenSuite]:
    bundle = task_path.parent
    baseline = read_model(bundle / "fix_baseline.json", FixBaseline)
    task = read_model(task_path, FixTask)
    if task != baseline.task or baseline.source.sha256 != task.before_source_sha256:
        raise ValueError("Task and local baseline identities differ")
    if (
        digest({k: v.model_dump() for k, v in baseline.source.files.items()})
        != baseline.source.sha256
    ):
        raise ValueError("Baseline source manifest checksum mismatch")
    for name, expected in [
        ("recorded_inputs.jsonl", baseline.recorded_inputs_sha256),
        ("before_requests.jsonl", baseline.before_requests_sha256),
        ("golden_before.jsonl", baseline.golden_before_sha256),
    ]:
        if file_sha(bundle / name) != expected:
            raise ValueError("Local baseline input checksum mismatch")
    suite = read_model(bundle / "golden_suite.json", GoldenSuite)
    if digest(suite) != task.golden_suite_sha256:
        raise ValueError("Golden suite changed after task preparation")
    validate_suite(suite)
    return baseline, suite


def verify_bundle(
    *,
    repo: Path,
    task_path: Path,
    report_path: Path,
    input_path: Path,
    tokenizer,
    quality_path: Path | None,
    review_paths: list[Path],
    test_timeout: int = 120,
    existing_tests: TestResult | None = None,
):
    baseline, suite = load_bundle(task_path)
    task = baseline.task
    if (
        file_sha(report_path) != task.report_sha256
        or file_sha(input_path) != baseline.recorded_inputs_sha256
        or tokenizer.identity != baseline.tokenizer_identity
    ):
        raise ValueError("Baseline report, inputs or tokenizer changed")
    bundle = task_path.parent
    records = read_recorded(bundle / "recorded_inputs.jsonl")
    before, _ = read_requests(bundle / "before_requests.jsonl")
    current = snapshot(repo, baseline.excluded_artifacts)
    changed, diff_hash = changes(baseline.source, current)
    signature_equal = builder_signature(repo) == baseline.builder_signature_sha256
    scope_ok = not (set(changed) - set(task.allowed_files))
    after_report = content = None
    quality = QualityStatus(status="not_run", reason="Code scope/signature must pass before replay")
    tests = TestResult(status="not_run", command=task.test_command, exit_code=None)
    after = []
    if scope_ok and signature_equal:
        after = render_in_repo(repo, records)
        templates = _templates(before, baseline.config.analysis)
        histories = {
            r["id"]: [Message.model_validate(m) for m in r["input"]["history"]] for r in records
        }
        content = check_content(before, after, templates, histories)
        encoded = "".join(canonical_json(r) + "\n" for r in after).encode()
        after_report = analyze(
            after, baseline.config, tokenizer, input_sha256=hashlib.sha256(encoded).hexdigest()
        )
        golden_before, _ = read_requests(bundle / "golden_before.jsonl")
        golden_after = render_in_repo(repo, _golden_records(suite))
        run = read_model(quality_path, QualityRun) if quality_path is not None else None
        reviews = [read_model(path, QualityReview) for path in review_paths]
        quality = evaluate_quality(
            run,
            task=task,
            after_source_sha256=current.sha256,
            diff_sha256=diff_hash,
            suite=suite,
            before=golden_before,
            after=golden_after,
            tokenizer=tokenizer,
            config=baseline.config,
            result_sha256=file_sha(quality_path) if quality_path is not None else None,
            reviews=reviews,
        )
        tests = (
            existing_tests
            if existing_tests is not None
            else run_tests(repo, task.test_command, timeout=test_timeout)
        )
    final = snapshot(repo, baseline.excluded_artifacts)
    result = assemble_verification(
        baseline,
        after_report=after_report,
        content=content,
        changed_files=changed,
        after_source_sha256=current.sha256,
        diff_sha256=diff_hash,
        signature_equal=signature_equal,
        tests=tests,
        quality=quality,
        quality_result_path=str(quality_path.resolve()) if quality_path else None,
        stable_source=final.sha256 == current.sha256,
    )
    return result, after, after_report


def default_allowed_files(repo: Path) -> list[str]:
    """Private planning is optional in a public checkout; public change records are not."""
    paths = ["demo_app/helpdesk/prompt.py", "CHANGELOG.md", "AI_USAGE.md"]
    if (repo / "DECISIONS.md").is_file():
        paths.append("DECISIONS.md")
    return paths


def approve_current(
    *,
    repo: Path,
    task_path: Path,
    report_path: Path,
    input_path: Path,
    verification_path: Path,
    tokenizer,
    review_paths: list[Path],
    reviewer: str,
    expected_diff_sha256: str,
    timestamp: str,
):
    """Shared CLI/API approval revalidation; a stored passed flag is insufficient."""
    from cachekit.fix.approve import approve
    from cachekit.fix.models import VerifyResult

    original = read_model(verification_path, VerifyResult)
    saved, _ = load_bundle(task_path)
    source = snapshot(repo, saved.excluded_artifacts)
    if (
        original.after_source_sha256 != source.sha256
        or original.task_sha256 != digest(saved.task)
        or original.tests.command != saved.task.test_command
        or original.tests.output_sha256 is None
        or original.quality_result_path is None
    ):
        raise ValueError("Verification is stale or incomplete; rerun verify")
    quality_path = Path(original.quality_result_path)
    fresh, _, _ = verify_bundle(
        repo=repo,
        task_path=task_path,
        report_path=report_path,
        input_path=input_path,
        tokenizer=tokenizer,
        quality_path=quality_path,
        review_paths=review_paths,
        existing_tests=original.tests,
    )
    if fresh != original:
        raise ValueError("Current evidence differs from verification; rerun verify")
    return approve(
        fresh,
        current_source_sha256=source.sha256,
        expected_diff_sha256=expected_diff_sha256,
        verify_sha256=file_sha(verification_path),
        quality_result_sha256=file_sha(quality_path),
        reviewer=reviewer,
        timestamp=timestamp,
    )
