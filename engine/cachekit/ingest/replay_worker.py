"""Trusted local worker imports the requested app, never contacts a service."""

import os
import socket
import sys

from cachekit.fix.models import RenderBatch, RenderResult
from cachekit.serialization import canonical_json


def main() -> None:
    payload = RenderBatch.model_validate_json(sys.stdin.read())

    def deny_network(*args, **kwargs):
        raise RuntimeError("Network access is forbidden during prompt replay")

    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    sys.path.insert(0, payload.repo)
    from demo_app.helpdesk.models import RecordedInput
    from demo_app.worker import render_record

    records = [RecordedInput.model_validate(r) for r in payload.records]
    if any(str(r.worker_seed) != os.environ.get("PYTHONHASHSEED") for r in records):
        raise ValueError("Replay worker seed mismatch")
    result = RenderResult(requests=[render_record(r) for r in records])
    sys.stdout.write(canonical_json(result))


if __name__ == "__main__":
    main()
