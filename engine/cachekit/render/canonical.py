"""Ordered inspection segments; actual model rendering uses its chat template."""

import json

from cachekit.models import Message, RequestRecord, Segment


def text_content(content: str | list[dict]) -> str:
    if isinstance(content, str):
        return content
    # Do not pretend multimodal placeholders are exact vLLM tokenization.
    raise ValueError("Only plain-text content is supported by the exact vLLM analysis path")


def model_messages(record: RequestRecord) -> list[Message]:
    messages = [message.model_copy(deep=True) for message in record.messages]
    if record.system is not None:
        messages.insert(0, Message(role="system", content=text_content(record.system)))
    for message in messages:
        text_content(message.content)
    return messages


def segments(record: RequestRecord) -> list[Segment]:
    result: list[Segment] = []
    if record.tools:
        result.append(
            Segment(
                kind="tools",
                index=0,
                text=json.dumps(
                    record.tools,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            )
        )
    if record.system is not None:
        result.append(
            Segment(kind="system", index=0, role="system", text=text_content(record.system))
        )
    for index, message in enumerate(record.messages):
        result.append(
            Segment(
                kind="message", index=index, role=message.role, text=text_content(message.content)
            )
        )
    return result


def segment_key(segment: Segment) -> str:
    return f"{segment.kind}:{segment.index}:{segment.role or ''}"
