"""Offline quality evaluation. Saved status booleans are never accepted as evidence."""

import json
import re

from cachekit.fix.models import (
    CaseEvaluation,
    FixTask,
    Generation,
    GoldenCase,
    GoldenSuite,
    QualityReview,
    QualityRun,
    QualityStatus,
    ToolCall,
)
from cachekit.fix.task import digest
from cachekit.models import RequestRecord
from cachekit.render.tokenize import PromptTokenizer, tokenize
from cachekit.settings import RunConfig


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Qwen chat-template tool blocks from a /completions response; never execute them."""
    calls = []
    blocks = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.S)
    if text.count("<tool_call>") != len(blocks):
        raise ValueError("Incomplete tool-call output")
    for block in blocks:
        try:
            value = json.loads(block)
            calls.append(ToolCall.model_validate(value))
        except Exception:
            raise ValueError("Invalid tool-call output; contents withheld") from None
    return calls


def prompt_identity(record: RequestRecord, tokenizer: PromptTokenizer) -> str:
    return digest(tokenize(record, tokenizer).token_ids)


def _json_valid(case: GoldenCase, output: Generation) -> bool | None:
    if case.output_json_schema is None:
        return None
    from jsonschema import Draft202012Validator

    try:
        value = json.loads(output.text)
        return Draft202012Validator(case.output_json_schema).is_valid(value)
    except (ValueError, TypeError):
        return False


def validate_suite(suite: GoldenSuite) -> None:
    """Validate declared checks before any inference; forbid external schema resolution."""

    def check_refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"} and (
                    not isinstance(child, str) or not child.startswith("#")
                ):
                    raise ValueError("Golden schemas cannot resolve external references")
                check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)

    for case in suite.cases:
        for assertion in case.assertions:
            if assertion.kind.startswith("text_"):
                if not assertion.pattern:
                    raise ValueError("Golden regex checks must have a nonempty pattern")
                re.compile(assertion.pattern)
        if case.output_json_schema is not None:
            from jsonschema import Draft202012Validator

            check_refs(case.output_json_schema)
            Draft202012Validator.check_schema(case.output_json_schema)


def _assertions(case: GoldenCase, output: Generation) -> dict[str, bool]:
    try:
        parsed = parse_tool_calls(output.text)
        # Re-derive tool calls rather than trusting a collector's claimed list.
        if parsed != output.tool_calls:
            return {check.id: False for check in case.assertions}
    except ValueError:
        return {check.id: False for check in case.assertions}
    names = {call.name for call in parsed}
    checks: dict[str, bool] = {}
    for check in case.assertions:
        if check.kind == "text_regex":
            passed = bool(re.search(check.pattern, output.text, re.I | re.M))
        elif check.kind == "text_not_regex":
            passed = not re.search(check.pattern, output.text, re.I | re.M)
        elif check.kind == "tools_allowed":
            passed = names <= set(check.tools)
        else:
            passed = not names.intersection(check.tools)
        checks[check.id] = bool(passed)
    return checks


def evaluate_quality(
    run: QualityRun | None,
    *,
    task: FixTask,
    after_source_sha256: str,
    diff_sha256: str,
    suite: GoldenSuite,
    before: list[RequestRecord],
    after: list[RequestRecord],
    tokenizer: PromptTokenizer,
    config: RunConfig,
    result_sha256: str | None,
    reviews: list[QualityReview] = (),
) -> QualityStatus:
    validate_suite(suite)
    if run is None:
        return QualityStatus(
            status="not_run", reason="No actual E5-lite inference artifact supplied"
        )
    stale = QualityStatus(
        status="stale",
        reason="Quality evidence identity does not match the fix",
        result_sha256=result_sha256,
    )
    if (
        run.task_sha256 != digest(task)
        or run.before_source_sha256 != task.before_source_sha256
        or run.after_source_sha256 != after_source_sha256
        or run.diff_sha256 != diff_sha256
        or run.golden_suite_sha256 != digest(suite)
        or digest(suite) != task.golden_suite_sha256
        or run.config_sha256 != task.config_sha256
        or run.tokenizer_identity != tokenizer.identity
        or run.generation != task.quality_generation
    ):
        return stale
    deployment = run.deployment
    if (
        deployment.model,
        deployment.revision,
        deployment.tokenizer_revision,
        deployment.vllm_version,
        deployment.max_model_len,
        deployment.block_size,
        deployment.capacity_blocks,
        deployment.gpu,
    ) != (
        config.vllm.model,
        config.vllm.revision,
        config.vllm.revision,
        config.vllm.version,
        config.vllm.max_model_len,
        config.vllm.block_size,
        config.vllm.capacity_blocks,
        "L4",
    ):
        return stale
    expected_ids = {c.id for c in suite.cases}
    if len({o.id for o in run.outputs}) != 5 or {o.id for o in run.outputs} != expected_ids:
        return stale
    old, new = {r.id: r for r in before}, {r.id: r for r in after}
    if set(old) != expected_ids or set(new) != expected_ids:
        return stale
    by_id = {o.id: o for o in run.outputs}
    evaluations = []
    failed = False
    for case in sorted(suite.cases, key=lambda c: c.id):
        output = by_id[case.id]
        if (
            output.before_prompt_sha256 != prompt_identity(old[case.id], tokenizer)
            or output.after_prompt_sha256 != prompt_identity(new[case.id], tokenizer)
            or output.before.prompt_tokens != len(tokenize(old[case.id], tokenizer).token_ids)
            or output.after.prompt_tokens != len(tokenize(new[case.id], tokenizer).token_ids)
        ):
            return stale
        exact = (output.before.text, output.before.tool_calls) == (
            output.after.text,
            output.after.tool_calls,
        )
        before_checks = _assertions(case, output.before)
        after_checks = _assertions(case, output.after)
        json_before, json_after = _json_valid(case, output.before), _json_valid(case, output.after)
        truncated = any(
            generation.finish_reason != "stop"
            or generation.completion_tokens > task.quality_generation.max_tokens
            for generation in (output.before, output.after)
        )
        failed |= not all(after_checks.values()) or json_after is False or truncated
        reviewed = any(
            review.quality_result_sha256 == result_sha256
            and review.case_id == case.id
            and review.before_output_sha256 == digest(output.before)
            and review.after_output_sha256 == digest(output.after)
            for review in reviews
        )
        evaluations.append(
            CaseEvaluation(
                id=case.id,
                exact_match=exact,
                before_assertions=before_checks,
                after_assertions=after_checks,
                json_before_valid=json_before,
                json_after_valid=json_after,
                truncated=truncated,
                reviewed=reviewed,
            )
        )
    if failed:
        status, reason = "failed", "An AFTER assertion, JSON check, or completion check failed"
    elif any(not c.exact_match and not c.reviewed for c in evaluations):
        status, reason = "review_required", "Changed golden outputs require explicit human review"
    else:
        status, reason = "passed", "All AFTER assertions pass; output differences are reviewed"
    return QualityStatus(
        status=status, reason=reason, result_sha256=result_sha256, cases=evaluations
    )
