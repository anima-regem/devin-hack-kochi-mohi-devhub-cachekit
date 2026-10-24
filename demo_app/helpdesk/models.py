"""Recorded helpdesk inputs, including every source of randomness."""

from typing import Literal, Self

from cachekit.models import BoundaryModel, JsonObject, Message
from pydantic import AwareDatetime, Field, model_validator

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"


class UserProfile(BoundaryModel):
    id: str
    name: str
    tier: Literal["standard", "premium", "business"] = "standard"
    locale: str = "en-IN"


class RetrievedDocument(BoundaryModel):
    id: str
    text: str


class HelpdeskInput(BoundaryModel):
    user: UserProfile
    history: list[Message] = Field(default_factory=list)
    retrieved_docs: list[RetrievedDocument] = Field(default_factory=list)
    message: str


class RecordedInput(BoundaryModel):
    id: str
    ts: float
    session_id: str
    input: HelpdeskInput
    now: AwareDatetime
    rng_seed: int = Field(ge=0)
    # PYTHONHASHSEED is part of the BEFORE builder's process-level tool order.
    worker_seed: int = Field(ge=0, le=4294967295)

    @model_validator(mode="after")
    def matching_timestamp(self) -> Self:
        if self.now.timestamp() != self.ts:
            raise ValueError("now and ts must describe the same instant")
        return self


class ChatRequest(BoundaryModel):
    model: str = MODEL_ID
    messages: list[Message]
    tools: list[JsonObject]
    temperature: float = 0
    max_tokens: int = 64
