"""Validated analysis configuration. File loading is confined to ingest/."""

from typing import Literal

from pydantic import Field

from cachekit.models import BoundaryModel


class VllmConfig(BoundaryModel):
    block_size: int = Field(gt=0)
    capacity_blocks: int = Field(gt=0)
    reserved_blocks: int = Field(ge=0)
    max_model_len: int = Field(gt=0)
    recompute_last_token: bool
    model: str
    revision: str
    version: str
    counter_unit: Literal["tokens"]
    full_blocks_only: Literal[True]
    concurrency_model: Literal["sequential"]


class AnalysisConfig(BoundaryModel):
    sample_limit: int = Field(ge=2, le=500)
    route_prefix_chars: int = Field(gt=0)
    high_stable_tokens: int = Field(ge=1)
    medium_stable_tokens: int = Field(ge=1)
    high_affected_fraction: float = Field(ge=0, le=1)
    large_hole_chars: int = Field(ge=1)
    min_anchor_chars: int = Field(ge=1)
    min_stable_tokens: int = Field(ge=0)
    heatmap_points: int = Field(ge=1, le=2000)
    redaction_patterns: list[str]


class RunConfig(BoundaryModel):
    vllm: VllmConfig
    analysis: AnalysisConfig
