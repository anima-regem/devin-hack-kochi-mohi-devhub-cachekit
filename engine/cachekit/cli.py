"""Local ingest and deterministic analysis commands."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from cachekit import __version__
from cachekit.cli_fix import register as register_fix_commands
from cachekit.ingest.config import load_config
from cachekit.ingest.jsonl import read_requests, write_requests
from cachekit.ingest.tokenizer import load_tokenizer
from cachekit.models import AnalysisRun, Report, RequestRecord
from cachekit.report import analyze as analyze_records
from cachekit.serialization import canonical_json

app = typer.Typer(no_args_is_help=True, help="Inspect and improve prompt-cache reuse.")


def show_version(value: bool) -> None:
    if value:
        typer.echo(f"cachekit {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool, typer.Option("--version", callback=show_version, is_eager=True)
    ] = False,
) -> None:
    """Deterministic prompt-cache analysis."""


class SchemaName(StrEnum):
    request = "RequestRecord"
    report = "Report"


@app.command()
def schema(model: Annotated[SchemaName, typer.Option()] = SchemaName.request) -> None:
    """Print the JSON schema for a shared file/API contract."""
    cls = RequestRecord if model == SchemaName.request else Report
    typer.echo(json.dumps(cls.model_json_schema(), sort_keys=True, indent=2))


class Source(StrEnum):
    jsonl = "jsonl"
    swe_agent = "swe-agent"
    glaive = "glaive"


@app.command()
def ingest(
    source: Annotated[Source, typer.Option()],
    input_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Option()],
    limit: Annotated[int, typer.Option(min=1)] = 100,
    seed: Annotated[int, typer.Option(min=0)] = 42,
    tool_order_fraction: Annotated[float, typer.Option(min=0, max=1)] = 0,
) -> None:
    """Convert a local file. Dataset limits count source rows/trajectories, not calls."""
    try:
        if source == Source.jsonl:
            records, _ = read_requests(input_path)
            records = records[:limit]
        elif source == Source.swe_agent:
            from cachekit.ingest.swe_agent import read_swe_agent

            records = read_swe_agent(input_path, limit=limit, seed=seed)
        else:
            from cachekit.ingest.glaive import read_glaive

            records = read_glaive(
                input_path, limit=limit, seed=seed, tool_order_fraction=tool_order_fraction
            )
        write_requests(records, out)
        typer.echo(f"Wrote {len(records)} requests to {out}")
    except Exception as error:
        # Validation exceptions may contain full private inputs. Do not echo them.
        typer.echo(f"Ingest failed ({type(error).__name__}); raw input content withheld", err=True)
        raise typer.Exit(1) from None


@app.command("analyze")
def analyze_command(
    input_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    tokenizer: Annotated[Path, typer.Option(help="Prefetched pinned local tokenizer directory.")],
    out: Annotated[Path, typer.Option()] = Path("eval_results/report.json"),
    backends: Annotated[str, typer.Option()] = "vllm",
    config_dir: Annotated[Path | None, typer.Option(exists=True, file_okay=False)] = None,
    block_size: Annotated[int | None, typer.Option(min=1)] = None,
    capacity_blocks: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Analyze local logs without inference, downloads, or network access."""
    if backends != "vllm":
        typer.echo("Only the vLLM profile is implemented. No fallback profile was used.", err=True)
        raise typer.Exit(1)
    try:
        config = load_config(config_dir)
        if block_size is not None:
            config.vllm.block_size = block_size
        if capacity_blocks is not None:
            config.vllm.capacity_blocks = capacity_blocks
        requests, input_hash = read_requests(input_path)
        loaded = load_tokenizer(tokenizer, model=config.vllm.model, revision=config.vllm.revision)
        report = analyze_records(requests, config, loaded, input_sha256=input_hash)
        payload = (canonical_json(report) + "\n").encode("utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(payload)
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
        metadata = AnalysisRun.model_validate(
            {
                "experiment": "offline_analysis",
                "timestamp": datetime.now(UTC).isoformat(),
                "git_sha": git.stdout.strip() if git.returncode == 0 else None,
                "git_sha_note": None if git.returncode == 0 else "No available repository commit",
                "git_dirty": bool(
                    subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        check=False,
                    ).stdout.strip()
                )
                if git.returncode == 0
                else None,
                "dataset": sorted({str(r.meta.get("source", "native-jsonl")) for r in requests}),
                "seed": {
                    key: sorted({int(r.meta[key]) for r in requests if key in r.meta})
                    for key in ("seed", "rng_seed", "worker_seed")
                },
                "n_requests": report.n_requests,
                "input_sha256": input_hash,
                "config_sha256": report.config_sha256,
                "report_sha256": hashlib.sha256(payload).hexdigest(),
                "model": config.vllm.model,
                "tokenizer": loaded.identity,
                "vllm_version": config.vllm.version,
                "block_size": config.vllm.block_size,
                "kv_capacity_tokens": config.vllm.capacity_blocks * config.vllm.block_size,
                "gpu": None,
                "repetitions": 1,
                "concurrency_model": "sequential",
                "note": (
                    "CPU simulation; vLLM version/capacity identify the configured profile, "
                    "not a live run. Generated traffic uses recorded per-request seeds. "
                    "No latency or dollar savings measured."
                ),
            }
        )
        out.with_suffix(".run.json").write_text(canonical_json(metadata) + "\n", encoding="utf-8")
        typer.echo(
            f"Analyzed {report.n_requests} requests; {len(report.findings)} findings. Report: {out}"
        )
        typer.echo("SIMULATED cache reuse; not a measured speedup or a verified fix.")
    except Exception as error:
        typer.echo(
            f"Analysis failed ({type(error).__name__}); no raw prompt content printed", err=True
        )
        if isinstance(error, ValueError) and not hasattr(error, "errors"):
            typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


register_fix_commands(app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
