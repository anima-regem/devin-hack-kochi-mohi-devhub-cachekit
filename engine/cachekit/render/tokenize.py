"""Pure model rendering/tokenization using an already loaded local tokenizer."""

from typing import Any, Protocol

from cachekit.models import BoundaryModel, JsonObject, RequestRecord
from cachekit.render.canonical import model_messages


class TokenizedRequest(BoundaryModel):
    id: str
    ts: float
    text: str
    token_ids: list[int]
    offsets: list[tuple[int, int]]
    namespace: str
    skip_cache_read: bool = False


class PromptTokenizer(Protocol):
    identity: JsonObject

    def render(self, record: RequestRecord) -> str: ...

    def encode_offsets(self, text: str) -> tuple[list[int], list[tuple[int, int]]]: ...


class HFPromptTokenizer:
    """The loader supplies a fast tokenizer; no file or network access here."""

    def __init__(self, tokenizer: Any, identity: JsonObject) -> None:
        self.tokenizer = tokenizer
        self.identity = identity

    def render(self, record: RequestRecord) -> str:
        messages = [m.model_dump(exclude_none=True) for m in model_messages(record)]
        return self.tokenizer.apply_chat_template(
            messages,
            tools=record.tools or None,
            tokenize=False,
            add_generation_prompt=True,
        )

    def encode_offsets(self, text: str) -> tuple[list[int], list[tuple[int, int]]]:
        encoded = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        return encoded["input_ids"], [tuple(pair) for pair in encoded["offset_mapping"]]


def tokenize(record: RequestRecord, tokenizer: PromptTokenizer) -> TokenizedRequest:
    from cachekit.serialization import canonical_json

    if any(key in record.params for key in ("lora_request", "lora_id", "multi_modal_data")):
        raise ValueError("LoRA and multimodal cache identities are not supported yet")
    text = tokenizer.render(record)
    token_ids, offsets = tokenizer.encode_offsets(text)
    namespace = canonical_json(
        {
            "model": tokenizer.identity.get("model", record.model),
            "cache_salt": record.params.get("cache_salt"),
        }
    )
    return TokenizedRequest(
        id=record.id,
        ts=record.ts,
        text=text,
        token_ids=token_ids,
        offsets=offsets,
        namespace=namespace,
        skip_cache_read=record.params.get("prompt_logprobs") is not None,
    )


def token_position(request: TokenizedRequest, char: int) -> int:
    return next(
        (index for index, (_, end) in enumerate(request.offsets) if end > char),
        len(request.token_ids),
    )


def count_span_tokens(request: TokenizedRequest, start: int, end: int) -> int:
    return sum(left < end and right > start for left, right in request.offsets)
