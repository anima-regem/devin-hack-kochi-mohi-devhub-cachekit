"""Shared JSON contracts from docs/02-ARCHITECTURE.md.

Models preserve input ordering. Rendering and report assembly will explicitly
sort only fields whose order has no semantic meaning.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

JsonObject = dict[str, JsonValue]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
Rate = Annotated[float, Field(ge=0, le=1)]
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AnalysisRun(BoundaryModel):
    """Saved run provenance; timestamps live here, outside the deterministic report."""

    experiment: Literal["offline_analysis"] = "offline_analysis"
    timestamp: str
    git_sha: str | None
    git_sha_note: str | None
    dataset: list[str]
    seed: dict[str, list[int]]
    n_requests: int = Field(ge=0)
    input_sha256: str
    config_sha256: str
    report_sha256: str
    model: str
    tokenizer: JsonObject
    vllm_version: str
    block_size: int = Field(gt=0)
    kv_capacity_tokens: int = Field(gt=0)
    gpu: None = None
    repetitions: Literal[1] = 1
    concurrency_model: Literal["sequential"] = "sequential"
    note: str


class Message(BoundaryModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[JsonObject]
    name: str | None = None
    tool_call_id: str | None = None


class RequestRecord(BoundaryModel):
    id: str = Field(min_length=1)
    ts: float
    session_id: str | None = None
    route: str | None = None
    provider: Literal["vllm", "openai", "anthropic", "unknown"] = "unknown"
    model: str | None = None
    tools: list[JsonObject] | None = None
    system: str | list[JsonObject] | None = None
    messages: list[Message] = Field(min_length=1)
    params: JsonObject = Field(default_factory=dict)
    meta: JsonObject = Field(default_factory=dict)


class Segment(BoundaryModel):
    kind: Literal["tools", "system", "message"]
    index: NonNegativeInt
    role: str | None = None
    text: str


class Hole(BoundaryModel):
    segment_kind: str
    segment_index: NonNegativeInt
    char_start: NonNegativeInt
    char_end: NonNegativeInt
    cardinality: NonNegativeInt
    sample_values: list[str] = Field(max_length=3)
    label: str

    @model_validator(mode="after")
    def check_span(self) -> Self:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class Finding(BoundaryModel):
    id: str = Field(min_length=1)
    route: str
    breaker: str
    severity: Literal["high", "medium", "low"]
    first_divergence_token: NonNegativeInt
    stable_tokens_after: NonNegativeInt
    requests_affected: NonNegativeInt
    tokens_wasted: NonNegativeInt
    waste_by_backend: dict[str, JsonObject]
    # Review-required findings use False; only explicit True permits a rewrite.
    safe_to_move: bool
    fix_hint: str
    evidence: list[str]
    code_locations: list[JsonObject] = Field(default_factory=list)


class BackendResult(BoundaryModel):
    backend: str
    params: JsonObject
    actual_hit_rate: Rate
    achievable_hit_rate: Rate
    tokens_recomputed_actual: NonNegativeInt
    tokens_recomputed_achievable: NonNegativeInt
    cost_actual: Annotated[float, Field(ge=0)] | None = None
    cost_achievable: Annotated[float, Field(ge=0)] | None = None


class Report(BoundaryModel):
    version: str
    input_sha256: SHA256
    config_sha256: SHA256
    n_requests: NonNegativeInt
    routes: list[str]
    backends: list[BackendResult]
    findings: list[Finding]
    heatmaps: dict[str, Annotated[list[Rate], Field(max_length=2000)]]
    template_preview: dict[str, str]
