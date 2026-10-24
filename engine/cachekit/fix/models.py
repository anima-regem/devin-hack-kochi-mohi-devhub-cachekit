"""Validated local fix, evidence, and approval contracts."""

from typing import Literal

from pydantic import Field, model_validator

from cachekit.models import SHA256, BoundaryModel, JsonObject, Rate, RequestRecord
from cachekit.settings import RunConfig


class SourceFile(BoundaryModel):
    sha256: SHA256
    executable: bool


class SourceSnapshot(BoundaryModel):
    files: dict[str, SourceFile]
    sha256: SHA256
    git_sha: str | None = None
    method: Literal["local_source_manifest_v1"] = "local_source_manifest_v1"


class TaskFinding(BoundaryModel):
    id: str
    breaker: str
    severity: Literal["high", "medium", "low"]
    first_divergence_token: int = Field(ge=0)
    stable_tokens_after: int = Field(ge=0)
    requests_affected: int = Field(ge=0)
    review_required: bool


class GenerationConfig(BoundaryModel):
    temperature: Literal[0] = 0
    max_tokens: int = Field(default=512, gt=0)
    seed: int = Field(default=42, ge=0)


class FixTask(BoundaryModel):
    version: Literal[1] = 1
    id: str
    repo_url: Literal["https://github.com/mohi-devhub/cachekit"]
    report_sha256: SHA256
    input_sha256: SHA256
    config_sha256: SHA256
    before_source_sha256: SHA256
    golden_suite_sha256: SHA256
    quality_generation: GenerationConfig
    findings: list[TaskFinding] = Field(min_length=1)
    routes: list[str]
    target_hit_rate: Rate
    allowed_files: list[str] = Field(min_length=1)
    test_command: list[str] = Field(min_length=1)
    builder_module: Literal["demo_app.helpdesk.prompt"] = "demo_app.helpdesk.prompt"
    builder_function: Literal["build_request"] = "build_request"


class FixBaseline(BoundaryModel):
    task: FixTask
    source: SourceSnapshot
    recorded_inputs_sha256: SHA256
    before_requests_sha256: SHA256
    golden_before_sha256: SHA256
    builder_signature_sha256: SHA256
    config: RunConfig
    tokenizer_identity: JsonObject
    baseline_hit_rate: Rate
    excluded_artifacts: list[str] = Field(default_factory=list)
    # Baseline is local-only. Its neighboring JSONL files contain private inputs.
    privacy: Literal["local_only"] = "local_only"


class GoldenAssertion(BoundaryModel):
    id: str
    kind: Literal["text_regex", "text_not_regex", "tools_allowed", "tools_forbidden"]
    pattern: str = ""
    tools: list[str] = Field(default_factory=list)


class GoldenCase(BoundaryModel):
    id: str
    category: Literal["time", "locale", "authorization", "retrieval", "continuity"]
    recorded_input: JsonObject
    assertions: list[GoldenAssertion] = Field(min_length=1)
    output_json_schema: JsonObject | None = None


class GoldenSuite(BoundaryModel):
    version: str
    public_synthetic: Literal[True]
    cases: list[GoldenCase] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def distinct_cases(self):
        if len({c.id for c in self.cases}) != 5:
            raise ValueError("Golden IDs must be unique")
        if {c.category for c in self.cases} != {
            "time",
            "locale",
            "authorization",
            "retrieval",
            "continuity",
        }:
            raise ValueError("Golden suite must cover all five required behaviors")
        for case in self.cases:
            if len({a.id for a in case.assertions}) != len(case.assertions):
                raise ValueError("Assertion IDs must be unique within a case")
        return self


class DeploymentIdentity(BoundaryModel):
    model: str
    revision: str
    tokenizer_revision: str
    vllm_version: str
    gpu: str
    max_model_len: int = Field(gt=0)
    block_size: int = Field(gt=0)
    capacity_blocks: int = Field(gt=0)
    deployment_id: str = Field(min_length=1)


class ToolCall(BoundaryModel):
    name: str
    arguments: JsonObject


class Generation(BoundaryModel):
    text: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class GoldenOutputs(BoundaryModel):
    id: str
    before: Generation
    after: Generation
    before_prompt_sha256: SHA256
    after_prompt_sha256: SHA256


class QualityRun(BoundaryModel):
    version: Literal[1] = 1
    experiment: Literal["E5-lite"] = "E5-lite"
    timestamp: str
    git_sha: str | None
    dataset: str = "public-synthetic-helpdesk-goldens"
    n_requests: Literal[10] = 10
    repetitions: Literal[1] = 1
    concurrency: Literal[1] = 1
    cachekit_version: str = "0.1.0"
    task_sha256: SHA256
    before_source_sha256: SHA256
    after_source_sha256: SHA256
    diff_sha256: SHA256
    golden_suite_sha256: SHA256
    config_sha256: SHA256
    tokenizer_identity: JsonObject
    generation: GenerationConfig
    deployment: DeploymentIdentity
    outputs: list[GoldenOutputs] = Field(min_length=5, max_length=5)
    note: str = "Actual synthetic golden inference; no external LLM judge."


class QualityReview(BoundaryModel):
    quality_result_sha256: SHA256
    case_id: str
    before_output_sha256: SHA256
    after_output_sha256: SHA256
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    timestamp: str


class CaseEvaluation(BoundaryModel):
    id: str
    exact_match: bool
    before_assertions: dict[str, bool]
    after_assertions: dict[str, bool]
    json_before_valid: bool | None
    json_after_valid: bool | None
    truncated: bool
    reviewed: bool


class QualityStatus(BoundaryModel):
    status: Literal["not_run", "stale", "failed", "review_required", "passed"]
    reason: str
    result_sha256: SHA256 | None = None
    cases: list[CaseEvaluation] = Field(default_factory=list)


class CheckResult(BoundaryModel):
    passed: bool
    details: list[str] = Field(default_factory=list)


class TestResult(BoundaryModel):
    status: Literal["passed", "failed", "not_run", "timeout"]
    command: list[str]
    exit_code: int | None
    # Test output can contain private fixtures; retain only its digest.
    output_sha256: SHA256 | None = None


class ContentResult(BoundaryModel):
    passed: bool
    n_requests: int
    missing_lines: int
    added_lines: int
    restored_history_lines: int = 0
    unexpected_added_lines: int = 0
    missing_dynamic_values: int
    tools_equal: bool
    envelope_equal: bool
    conversation_roles_preserved: bool = True
    note: str = "Order-insensitive normalized line multisets; semantic safety is a separate gate."


class VerifyResult(BoundaryModel):
    version: Literal[1] = 1
    task_id: str
    task_sha256: SHA256
    passed: bool
    hit_rate_before: Rate
    hit_rate_after: Rate | None
    target_hit_rate: Rate
    content_check: ContentResult | None
    prefix_check: CheckResult
    scope_check: CheckResult
    signature_check: CheckResult
    tests: TestResult
    quality_guard: QualityStatus
    before_source_sha256: SHA256
    after_source_sha256: SHA256
    diff_sha256: SHA256
    inputs_sha256: SHA256
    config_sha256: SHA256
    changed_files: list[str]
    quality_result_path: str | None
    note: str = "Cache rates are SIMULATED; passing goldens supports only the tested behaviors."


class VerificationRun(BoundaryModel):
    experiment: Literal["fix_verification"] = "fix_verification"
    timestamp: str
    git_sha: str | None
    source_sha256: SHA256
    diff_sha256: SHA256
    task_sha256: SHA256
    config_sha256: SHA256
    inputs_sha256: SHA256
    verify_sha256: SHA256
    model: str
    revision: str
    tokenizer: JsonObject
    vllm_version: str
    gpu: None = None
    n_requests: int = Field(ge=0)
    dataset: Literal["recorded-helpdesk-inputs"] = "recorded-helpdesk-inputs"
    seed: dict[str, list[int]]
    note: str = "CPU verification and simulation. No inference or Devin session started by verify."


class Approval(BoundaryModel):
    reviewer: str = Field(min_length=1)
    timestamp: str
    task_id: str
    diff_sha256: SHA256
    before_source_sha256: SHA256
    after_source_sha256: SHA256
    verify_sha256: SHA256
    quality_result_sha256: SHA256


class FixResult(BoundaryModel):
    task_id: str
    status: Literal["prepared", "running", "finished", "failed", "timeout"]
    branch: str | None = None
    pr_url: str | None = None
    session_id: str | None = None
    session_url: str | None = None
    log: list[str] = Field(default_factory=list)


class RenderBatch(BoundaryModel):
    repo: str
    records: list[JsonObject]


class RenderResult(BoundaryModel):
    requests: list[RequestRecord]
