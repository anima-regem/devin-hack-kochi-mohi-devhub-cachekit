"""Seeded synthetic traffic with reproducible process-level tool ordering.

Run from the workspace: uv run python -m demo_app.traffic --out data/demo
No inference, network, or wall-clock time is used by this generator.
"""

import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import Annotated, Literal

import typer
from cachekit.models import BoundaryModel, Message, RequestRecord
from cachekit.serialization import canonical_json
from pydantic import Field

from demo_app.helpdesk.catalog import QUESTIONS
from demo_app.helpdesk.models import HelpdeskInput, RecordedInput, RetrievedDocument, UserProfile

app = typer.Typer(help="Generate fictional BEFORE logs and inputs for exact re-rendering.")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_START = datetime(2026, 10, 24, 11, 30, tzinfo=UTC).timestamp()


class TrafficConfig(BoundaryModel):
    users: int = Field(default=200, ge=1)
    seed: int = Field(default=42, ge=0)
    workers: int = Field(default=3, ge=1, le=16)
    min_turns: int = Field(default=2, ge=2, le=10)
    max_turns: int = Field(default=10, ge=2, le=10)
    start_ts: float = DEFAULT_START
    mean_session_gap: float = Field(default=1, gt=0)
    mean_turn_gap: float = Field(default=8, gt=0)


class TrafficManifest(BoundaryModel):
    source: Literal["synthetic-helpdesk"] = "synthetic-helpdesk"
    config: TrafficConfig
    n_requests: int
    inputs_sha256: str
    requests_sha256: str
    note: str = "Synthetic fixture metadata, not benchmark measurements."


def generate_inputs(config: TrafficConfig) -> list[RecordedInput]:
    """Create all session inputs in memory using only the supplied configuration."""
    if config.min_turns > config.max_turns:
        raise ValueError("min_turns must not exceed max_turns")
    rng = Random(config.seed)
    session_start = config.start_ts
    records: list[RecordedInput] = []
    tiers = ("standard", "premium", "business")
    for user_index in range(config.users):
        if user_index:
            session_start += rng.expovariate(1 / config.mean_session_gap)
        arrival = session_start
        session_id = f"helpdesk-{user_index:04d}"
        user = UserProfile(
            id=f"customer-{user_index:04d}",
            name=f"Customer {user_index:04d}",
            tier=tiers[user_index % len(tiers)],
        )
        history: list[Message] = []
        for turn in range(rng.randint(config.min_turns, config.max_turns)):
            if turn:
                arrival += rng.expovariate(1 / config.mean_turn_gap)
            # Round-trip through datetime once so the two timestamp fields are exact.
            now = datetime.fromtimestamp(arrival, tz=UTC)
            question = rng.choice(QUESTIONS)
            reference = f"{session_id}-turn-{turn:02d}"
            retrieved = RetrievedDocument(
                id=f"case-note-{reference}",
                text=(
                    f"Fictional retrieved support note {reference}. "
                    f"The customer is asking: {question} "
                    "The order state must be checked before selecting a remedy. "
                    "No refund, replacement, return, or delivery investigation has been "
                    "authorized by this note. Refer to the company handbook for the "
                    "applicable eligibility and confirmation requirements. "
                    f"Retrieval reference: {reference}."
                ),
            )
            records.append(
                RecordedInput(
                    id=f"demo-{user_index:04d}-{turn:02d}",
                    ts=now.timestamp(),
                    session_id=session_id,
                    input=HelpdeskInput(
                        user=user.model_copy(deep=True),
                        history=[message.model_copy(deep=True) for message in history],
                        retrieved_docs=[retrieved],
                        message=question,
                    ),
                    now=now,
                    rng_seed=rng.randrange(2**32),
                    worker_seed=(config.seed + user_index % config.workers) % 2**32,
                )
            )
            history.extend(
                [
                    Message(role="user", content=question),
                    Message(
                        role="assistant",
                        content=(
                            "Synthetic conversation reply: I can check the relevant order record."
                        ),
                    ),
                ]
            )
    return sorted(records, key=lambda record: (record.ts, record.id))


def _render_worker(batch: list[RecordedInput], builder_version: str) -> list[RequestRecord]:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(batch[0].worker_seed)
    env["CACHEKIT_DEMO_BUILDER"] = builder_version
    # Source paths also support offline execution before the editable install.
    source_paths = [str(REPO_ROOT), str(REPO_ROOT / "engine")]
    if env.get("PYTHONPATH"):
        source_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(source_paths)
    completed = subprocess.run(
        [sys.executable, "-m", "demo_app.worker"],
        input="".join(canonical_json(record) + "\n" for record in batch),
        text=True,
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=120,
        check=False,
    )
    if completed.returncode:
        # Do not echo worker stderr: a validation error may include raw input text.
        raise RuntimeError(f"Rendering worker failed with exit code {completed.returncode}")
    return [RequestRecord.model_validate_json(line) for line in completed.stdout.splitlines()]


def render_inputs(
    records: list[RecordedInput], *, builder_version: str = "current"
) -> list[RequestRecord]:
    if not records:
        return []
    if len({record.id for record in records}) != len(records):
        raise ValueError("Recorded input IDs must be unique")
    batches: dict[int, list[RecordedInput]] = {}
    for record in records:
        batches.setdefault(record.worker_seed, []).append(record)
    with ThreadPoolExecutor(max_workers=min(len(batches), 16)) as pool:
        rendered_batches = pool.map(
            _render_worker,
            [batches[key] for key in sorted(batches)],
            [builder_version] * len(batches),
        )
        rendered = [record for batch in rendered_batches for record in batch]
    return sorted(rendered, key=lambda record: (record.ts, record.id))


def write_traffic(config: TrafficConfig, out: Path) -> TrafficManifest:
    records = generate_inputs(config)
    requests = render_inputs(records, builder_version="before")
    inputs_bytes = "".join(canonical_json(record) + "\n" for record in records).encode("utf-8")
    requests_bytes = "".join(canonical_json(record) + "\n" for record in requests).encode("utf-8")
    manifest = TrafficManifest(
        config=config,
        n_requests=len(requests),
        inputs_sha256=hashlib.sha256(inputs_bytes).hexdigest(),
        requests_sha256=hashlib.sha256(requests_bytes).hexdigest(),
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "inputs.jsonl").write_bytes(inputs_bytes)
    (out / "requests_before.jsonl").write_bytes(requests_bytes)
    (out / "manifest.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    return manifest


@app.command()
def generate(
    out: Annotated[Path, typer.Option(help="Output directory; keep raw logs gitignored.")] = Path(
        "data/demo"
    ),
    users: Annotated[int, typer.Option(min=1)] = 200,
    seed: Annotated[int, typer.Option(min=0)] = 42,
    workers: Annotated[int, typer.Option(min=1, max=16)] = 3,
) -> None:
    manifest = write_traffic(TrafficConfig(users=users, seed=seed, workers=workers), out)
    typer.echo(f"Wrote {manifest.n_requests} synthetic requests and recorded inputs to {out}")
    typer.echo("These are generated fixtures, not measured benchmark results.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
