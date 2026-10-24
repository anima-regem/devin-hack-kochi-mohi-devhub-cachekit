"""Pure human approval record; the I/O caller revalidates current evidence first."""

from cachekit.fix.models import Approval, VerifyResult


def approve(
    result: VerifyResult,
    *,
    current_source_sha256: str,
    expected_diff_sha256: str,
    verify_sha256: str,
    quality_result_sha256: str,
    reviewer: str,
    timestamp: str,
) -> Approval:
    if (
        not result.passed
        or result.quality_guard.status != "passed"
        or result.tests.status != "passed"
        or result.tests.exit_code != 0
        or not result.scope_check.passed
        or not result.signature_check.passed
        or not result.prefix_check.passed
        or result.content_check is None
        or not result.content_check.passed
        or not result.changed_files
    ):
        raise ValueError("Approval requires all verification gates to pass")
    if (
        result.diff_sha256 != expected_diff_sha256
        or result.after_source_sha256 != current_source_sha256
        or result.quality_guard.result_sha256 != quality_result_sha256
    ):
        raise ValueError("Approval evidence or exact diff is stale")
    return Approval(
        reviewer=reviewer,
        timestamp=timestamp,
        task_id=result.task_id,
        diff_sha256=result.diff_sha256,
        before_source_sha256=result.before_source_sha256,
        after_source_sha256=result.after_source_sha256,
        verify_sha256=verify_sha256,
        quality_result_sha256=quality_result_sha256,
    )
