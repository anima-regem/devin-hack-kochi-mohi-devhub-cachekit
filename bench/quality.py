"""Collect actual E5-lite outputs on local vLLM or Modal. Never invoked by verify.

Run with: python -m bench.quality --help
Only the task's fixed public synthetic golden requests can be submitted.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import httpx
import typer
from cachekit.fix.models import DeploymentIdentity, Generation, GoldenOutputs, QualityRun
from cachekit.fix.quality import parse_tool_calls, prompt_identity
from cachekit.fix.task import digest
from cachekit.ingest.fix import changes, read_model, render_in_repo, snapshot
from cachekit.ingest.fix_workflow import _golden_records, load_bundle
from cachekit.ingest.jsonl import read_requests
from cachekit.ingest.tokenizer import load_tokenizer
from cachekit.models import BoundaryModel
from cachekit.render.tokenize import tokenize
from cachekit.serialization import canonical_json
from pydantic import BaseModel, ConfigDict, Field

app = typer.Typer()


class CompletionRequest(BoundaryModel):
    model: str
    prompt: list[int]
    temperature: int
    max_tokens: int
    seed: int
    skip_special_tokens: bool = False


class Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    finish_reason: str


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class CompletionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str
    choices: list[Choice] = Field(min_length=1, max_length=1)
    usage: Usage


class VersionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: str


class ServedModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    max_model_len: int | None = None


class ModelsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: list[ServedModel]


def validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    modal = bool(parsed.hostname and parsed.hostname.endswith(".modal.run"))
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or not (
            (local and parsed.scheme in {"http", "https"}) or (modal and parsed.scheme == "https")
        )
    ):
        raise ValueError("Quality inference requires a local vLLM or HTTPS Modal base URL")
    return endpoint.rstrip("/")


def collect_quality(
    *,
    repo: Path,
    task_path: Path,
    endpoint: str,
    deployment: DeploymentIdentity,
    tokenizer,
    client: httpx.Client,
) -> QualityRun:
    endpoint = validate_endpoint(endpoint)
    baseline, suite = load_bundle(task_path)
    task = baseline.task
    if tokenizer.identity != baseline.tokenizer_identity:
        raise ValueError("Tokenizer identity differs from the task baseline")
    current = snapshot(repo, baseline.excluded_artifacts)
    changed, diff_hash = changes(baseline.source, current)
    if not changed or set(changed) - set(task.allowed_files):
        raise ValueError(
            "Quality collection requires a candidate diff within the task's allowed files"
        )
    config = baseline.config.vllm
    if (
        deployment.model,
        deployment.revision,
        deployment.tokenizer_revision,
        deployment.vllm_version,
        deployment.max_model_len,
        deployment.block_size,
        deployment.capacity_blocks,
        deployment.gpu,
    ) != (
        config.model,
        config.revision,
        config.revision,
        config.version,
        config.max_model_len,
        config.block_size,
        config.capacity_blocks,
        "L4",
    ):
        raise ValueError("Deployment manifest does not match the selected benchmark profile")
    version_response = client.get(endpoint + "/version")
    model_response = client.get(endpoint + "/v1/models")
    version_response.raise_for_status()
    model_response.raise_for_status()
    version = VersionResponse.model_validate(version_response.json())
    models = ModelsResponse.model_validate(model_response.json())
    if version.version != deployment.vllm_version:
        raise ValueError("Live vLLM version differs from the deployment manifest")
    served = next((m for m in models.data if m.id == deployment.model), None)
    if served is None:
        raise ValueError("Live served model differs from the deployment manifest")
    if served.max_model_len is not None and served.max_model_len != deployment.max_model_len:
        raise ValueError("Live context limit differs from the deployment manifest")
    before, _ = read_requests(task_path.parent / "golden_before.jsonl")
    after = render_in_repo(repo, _golden_records(suite))
    old, new = {r.id: r for r in before}, {r.id: r for r in after}
    outputs = []

    def generate(record) -> Generation:
        tokens = tokenize(record, tokenizer).token_ids
        if len(tokens) + task.quality_generation.max_tokens > deployment.max_model_len:
            raise ValueError("Golden prompt and output budget exceed the model context limit")
        payload = CompletionRequest(
            model=deployment.model, prompt=tokens, **task.quality_generation.model_dump()
        )
        response = client.post(endpoint + "/v1/completions", json=payload.model_dump())
        response.raise_for_status()
        parsed = CompletionResponse.model_validate(response.json())
        if parsed.model != deployment.model or parsed.usage.prompt_tokens != len(tokens):
            raise ValueError("Inference response model/token accounting differs from the request")
        choice = parsed.choices[0]
        # Remove only the model's terminal message marker; retain tool-call delimiters.
        text = choice.text.removesuffix("<|im_end|>").removesuffix("<|endoftext|>")
        return Generation(
            text=text,
            tool_calls=parse_tool_calls(text),
            finish_reason=choice.finish_reason,
            prompt_tokens=parsed.usage.prompt_tokens,
            completion_tokens=parsed.usage.completion_tokens,
        )

    for case in sorted(suite.cases, key=lambda c: c.id):
        outputs.append(
            GoldenOutputs(
                id=case.id,
                before=generate(old[case.id]),
                after=generate(new[case.id]),
                before_prompt_sha256=prompt_identity(old[case.id], tokenizer),
                after_prompt_sha256=prompt_identity(new[case.id], tokenizer),
            )
        )
    if snapshot(repo, baseline.excluded_artifacts).sha256 != current.sha256:
        raise ValueError("Source changed during quality inference; results are stale")
    return QualityRun(
        timestamp=datetime.now(UTC).isoformat(),
        git_sha=current.git_sha,
        task_sha256=digest(task),
        before_source_sha256=baseline.source.sha256,
        after_source_sha256=current.sha256,
        diff_sha256=diff_hash,
        golden_suite_sha256=digest(suite),
        config_sha256=task.config_sha256,
        tokenizer_identity=tokenizer.identity,
        generation=task.quality_generation,
        deployment=deployment,
        outputs=outputs,
        note="Actual public synthetic golden inference via /v1/completions and exact token IDs. "
        "Deployment revision/GPU identity comes from the operator's deployment manifest; "
        "live version/model IDs are checked. No external LLM judge.",
    )


@app.command()
def run(
    task: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    endpoint: Annotated[str, typer.Option()],
    deployment_manifest: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Option()],
    repo: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    tokenizer: Annotated[Path, typer.Option()] = Path("data/tokenizer"),
) -> None:
    """Run live synthetic golden inference explicitly; requires a real deployment manifest."""
    try:
        if out.exists():
            raise ValueError("Quality result already exists; select a new immutable run path")
        baseline, _ = load_bundle(task)
        loaded = load_tokenizer(
            tokenizer, model=baseline.config.vllm.model, revision=baseline.config.vllm.revision
        )
        deployment = read_model(deployment_manifest, DeploymentIdentity)
        with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:
            result = collect_quality(
                repo=repo,
                task_path=task,
                endpoint=endpoint,
                deployment=deployment,
                tokenizer=loaded,
                client=client,
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as handle:
            handle.write(canonical_json(result) + "\n")
        typer.echo(f"Saved actual E5-lite outputs: {out}. Run cachekit verify to evaluate them.")
    except Exception as error:
        typer.echo(
            f"Quality inference failed ({type(error).__name__}); responses withheld", err=True
        )
        if isinstance(error, ValueError) and not hasattr(error, "errors"):
            typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
