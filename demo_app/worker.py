"""Internal subprocess entrypoint; PYTHONHASHSEED must be set before Python starts."""

import os
import sys
from random import Random

from cachekit.models import RequestRecord
from cachekit.serialization import canonical_json

from demo_app.helpdesk.models import ChatRequest, RecordedInput
from demo_app.helpdesk.prompt import build_request


def render_record(record: RecordedInput, *, builder_version: str = "current") -> RequestRecord:
    if os.environ.get("PYTHONHASHSEED") != str(record.worker_seed):
        raise ValueError("Run in a subprocess with the recorded PYTHONHASHSEED")
    builder = build_request
    if builder_version == "before":
        from demo_app.helpdesk.before import build_request as before_builder

        builder = before_builder
    elif builder_version != "current":
        raise ValueError("Unsupported builder version")
    request = ChatRequest.model_validate(
        builder(record.input, now=record.now, rng=Random(record.rng_seed))
    )
    planted = ["timestamp", "user_identity", "tool_order", "few_shot_sampling", "rag_before_static"]
    if len(record.input.history) > 6:
        planted.append("history_truncation")
    return RequestRecord(
        id=record.id,
        ts=record.ts,
        session_id=record.session_id,
        route="helpdesk.answer",
        provider="vllm",
        model=request.model,
        messages=request.messages,
        tools=request.tools,
        params={"temperature": request.temperature, "max_tokens": request.max_tokens},
        meta={
            "source": "synthetic-helpdesk",
            "app_version": builder_version,
            "rng_seed": record.rng_seed,
            "worker_seed": record.worker_seed,
            "planted": planted,
        },
    )


def main() -> None:
    for line in sys.stdin:
        if line.strip():
            record = RecordedInput.model_validate_json(line)
            version = os.environ.get("CACHEKIT_DEMO_BUILDER", "current")
            sys.stdout.write(canonical_json(render_record(record, builder_version=version)) + "\n")


if __name__ == "__main__":
    main()
