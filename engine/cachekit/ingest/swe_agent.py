"""Convert local Nebius trajectories without downloading or evaluating anything."""

import hashlib
from pathlib import Path
from random import Random

from pydantic import Field

from cachekit.models import BoundaryModel, Message, RequestRecord


class TrajectoryStep(BoundaryModel):
    role: str
    system_prompt: str | None = None
    text: str | None = None
    cutoff_date: str | None = None
    mask: bool | None = None


class Trajectory(BoundaryModel):
    instance_id: str
    model_name: str | None = None
    trajectory: list[TrajectoryStep]


class ArrivalConfig(BoundaryModel):
    seed: int = Field(ge=0)
    start_ts: float = 0
    mean_step_gap: float = Field(default=8, gt=0)
    mean_session_gap: float = Field(default=1, gt=0)


def convert_trajectory(
    row: Trajectory, *, index: int, arrival: float, rng: Random, timing: ArrivalConfig
) -> list[RequestRecord]:
    messages: list[Message] = []
    requests: list[RequestRecord] = []
    identity = hashlib.sha256(f"{row.instance_id}:{index}".encode()).hexdigest()[:16]
    for step in row.trajectory:
        if step.role == "system":
            content = step.system_prompt or step.text or ""
            messages.append(Message(role="system", content=content))
        elif step.role in {"user", "tool", "observation"}:
            # The dataset represents environment observations as user turns.
            messages.append(Message(role="user", content=step.text or ""))
        elif step.role in {"ai", "assistant"}:
            if not messages:
                raise ValueError("Trajectory has an assistant step without preceding context")
            requests.append(
                RequestRecord(
                    id=f"swe-{identity}-{len(requests):04d}",
                    ts=arrival,
                    session_id=f"swe-{identity}",
                    route="swe-agent.step",
                    model=row.model_name,
                    messages=[message.model_copy(deep=True) for message in messages],
                    meta={
                        "source": "nebius/SWE-agent-trajectories",
                        "seed": timing.seed,
                        "synthetic_arrivals": True,
                    },
                )
            )
            messages.append(Message(role="assistant", content=step.text or ""))
            arrival += rng.expovariate(1 / timing.mean_step_gap)
        else:
            raise ValueError("Unsupported trajectory role; input content withheld")
    return requests


def read_swe_agent(path: Path, *, limit: int, seed: int) -> list[RequestRecord]:
    import pyarrow.parquet as pq

    rng = Random(seed)
    timing = ArrivalConfig(seed=seed)
    arrival = timing.start_ts
    output: list[RequestRecord] = []
    count = 0
    for batch in pq.ParquetFile(path).iter_batches(
        batch_size=min(limit, 64), columns=["instance_id", "model_name", "trajectory"]
    ):
        for raw in batch.to_pylist():
            row = Trajectory.model_validate(raw)
            output.extend(
                convert_trajectory(row, index=count, arrival=arrival, rng=rng, timing=timing)
            )
            count += 1
            arrival += rng.expovariate(1 / timing.mean_session_gap)
            if count >= limit:
                return sorted(output, key=lambda record: (record.ts, record.id))
    return sorted(output, key=lambda record: (record.ts, record.id))
