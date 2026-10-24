"""Pure acceptance assembly; no imports of patched code, subprocesses or inference."""

from cachekit.fix.models import (
    CheckResult,
    ContentResult,
    FixBaseline,
    QualityStatus,
    TestResult,
    VerifyResult,
)
from cachekit.fix.task import digest
from cachekit.models import Report


def assemble_verification(
    baseline: FixBaseline,
    *,
    after_report: Report | None,
    content: ContentResult | None,
    changed_files: list[str],
    after_source_sha256: str,
    diff_sha256: str,
    signature_equal: bool,
    tests: TestResult,
    quality: QualityStatus,
    quality_result_path: str | None,
    stable_source: bool,
) -> VerifyResult:
    task = baseline.task
    forbidden = sorted(set(changed_files) - set(task.allowed_files))
    scope = CheckResult(
        passed=not forbidden and stable_source,
        details=forbidden + ([] if stable_source else ["Source changed during checks"]),
    )
    signature = CheckResult(
        passed=signature_equal, details=[] if signature_equal else ["Builder signature changed"]
    )
    hit_rate = None
    prefix_ok = False
    remaining = []
    if after_report is not None:
        backend = next(b for b in after_report.backends if b.backend == "vllm")
        hit_rate = backend.actual_hit_rate
        types = {f.breaker for f in task.findings}
        remaining = sorted(
            {
                f.breaker
                for f in after_report.findings
                if f.breaker in types and f.severity == "high"
            }
        )
        prefix_ok = hit_rate >= task.target_hit_rate and not remaining
    prefix = CheckResult(passed=prefix_ok, details=remaining)
    passed = bool(changed_files) and all(
        [
            scope.passed,
            signature.passed,
            prefix.passed,
            content is not None and content.passed,
            tests.status == "passed" and tests.exit_code == 0,
            quality.status == "passed",
        ]
    )
    return VerifyResult(
        task_id=task.id,
        task_sha256=digest(task),
        passed=passed,
        hit_rate_before=baseline.baseline_hit_rate,
        hit_rate_after=hit_rate,
        target_hit_rate=task.target_hit_rate,
        content_check=content,
        prefix_check=prefix,
        scope_check=scope,
        signature_check=signature,
        tests=tests,
        quality_guard=quality,
        before_source_sha256=baseline.source.sha256,
        after_source_sha256=after_source_sha256,
        diff_sha256=diff_sha256,
        inputs_sha256=baseline.recorded_inputs_sha256,
        config_sha256=task.config_sha256,
        changed_files=changed_files,
        quality_result_path=quality_result_path,
    )
