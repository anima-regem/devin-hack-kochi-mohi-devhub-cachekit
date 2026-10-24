"""Fix workflow CLI. File, subprocess and optional fixer I/O stay out of analysis."""

import os
import shlex
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr

from cachekit.fix.approve import approve as make_approval
from cachekit.fix.models import (
    FixResult,
    GenerationConfig,
    QualityReview,
    QualityRun,
    VerificationRun,
    VerifyResult,
)
from cachekit.fix.task import digest, task_markdown
from cachekit.ingest.config import load_config
from cachekit.ingest.fix import file_sha, read_model, read_recorded, snapshot, write_model
from cachekit.ingest.fix_workflow import load_bundle, prepare_task, verify_bundle
from cachekit.ingest.jsonl import write_requests
from cachekit.ingest.tokenizer import load_tokenizer


@contextmanager
def checked():
    try:
        yield
    except typer.Exit:
        raise
    except Exception as error:
        typer.echo(
            f"Fix workflow failed ({type(error).__name__}); input content withheld", err=True
        )
        if isinstance(error, ValueError) and not hasattr(error, "errors"):
            typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


def _tokenizer(path: Path, config):
    return load_tokenizer(path, model=config.vllm.model, revision=config.vllm.revision)


def _devin(repo: Path, api_version: str, max_acu_limit: int):
    # Called only after the explicit session approval gate, never on local handoff.
    from dotenv import dotenv_values

    from cachekit.fix.devin import DevinFixer

    values = dotenv_values(repo / ".env", interpolate=False)
    token = os.environ.get("DEVIN_API_KEY") or values.get("DEVIN_API_KEY")
    org = os.environ.get("DEVIN_ORG_ID") or values.get("DEVIN_ORG_ID")
    if not token:
        raise ValueError("DEVIN_API_KEY is missing; its value was not printed")
    return DevinFixer(
        token=SecretStr(token), api_version=api_version, org_id=org, max_acu_limit=max_acu_limit
    )


def register(app: typer.Typer) -> None:
    @app.command("task")
    def task_command(
        report: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
        repo: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
        inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
            "data/demo/inputs.jsonl"
        ),
        before_requests: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
            "data/demo/requests_before.jsonl"
        ),
        goldens: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
            "demo_app/goldens.json"
        ),
        tokenizer: Annotated[Path, typer.Option()] = Path("data/tokenizer"),
        out: Annotated[Path, typer.Option()] = Path("data/fixes/demo/fix_task.md"),
        finding: Annotated[list[str] | None, typer.Option()] = None,
        allow_file: Annotated[list[str] | None, typer.Option()] = None,
        test_command: Annotated[str, typer.Option()] = "python3 -m pytest -q",
        quality_max_tokens: Annotated[int, typer.Option(min=1)] = 512,
        config_dir: Annotated[Path | None, typer.Option()] = None,
    ) -> None:
        """Prepare an immutable local baseline and a redacted agent task; no agent starts."""
        with checked():
            if out.name != "fix_task.md":
                raise ValueError(
                    "Task output must be named fix_task.md inside a new bundle directory"
                )
            config = load_config(config_dir)
            loaded = _tokenizer(tokenizer, config)
            baseline = prepare_task(
                repo=repo,
                report_path=report,
                input_path=inputs,
                before_path=before_requests,
                suite_path=goldens,
                bundle=out.parent,
                config=config,
                tokenizer=loaded,
                allowed_files=allow_file
                or ["demo_app/helpdesk/prompt.py", "DECISIONS.md", "CHANGELOG.md", "AI_USAGE.md"],
                test_command=shlex.split(test_command),
                finding_ids=finding,
                generation=GenerationConfig(max_tokens=quality_max_tokens),
            )
            write_model(out.with_suffix(".json"), baseline.task)
            write_model(out.parent / "fix_baseline.json", baseline)
            out.write_text(task_markdown(baseline.task), encoding="utf-8")
            typer.echo(f"Prepared redacted task {baseline.task.id}: {out}")
            typer.echo("Neighboring baseline/JSONL files are local-only. No fixer was started.")

    @app.command("fix")
    def fix_command(
        task: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
        repo: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
        fixer: Annotated[str, typer.Option()] = "local",
        out: Annotated[Path, typer.Option()] = Path("eval_results/fix_handoff.json"),
        approve_devin_session: Annotated[bool, typer.Option()] = False,
        api_version: Annotated[str, typer.Option()] = "v3",
        max_acu_limit: Annotated[int | None, typer.Option(min=1)] = None,
    ) -> None:
        """Prepare local handoff, or explicitly approve and create one bounded Devin session."""
        with checked():
            baseline, _ = load_bundle(task)
            if snapshot(repo, baseline.excluded_artifacts).sha256 != baseline.source.sha256:
                raise ValueError(
                    "Source changed since the task was prepared; do not start a stale task"
                )
            if fixer == "local":
                from cachekit.fix.local_agent import LocalAgentFixer

                result = LocalAgentFixer().run(baseline.task, repo)
            elif fixer == "devin":
                if not approve_devin_session:
                    raise ValueError(
                        "Mohith must explicitly approve a Devin session; none was started"
                    )
                if api_version not in {"v1", "v3"} or max_acu_limit is None:
                    raise ValueError(
                        "Select a documented API version and an explicit positive ACU cap"
                    )
                if out.exists():
                    raise ValueError(
                        "Session result already exists; inspect it before creating another session"
                    )
                client = _devin(repo, api_version, max_acu_limit)
                result = client.run(baseline.task, repo, approved=True)
            else:
                raise ValueError("Choose local or devin")
            write_model(out, result)
            typer.echo(f"Fixer status: {result.status}. Result: {out}")
            if result.branch:
                typer.echo(f"Proposed branch: {result.branch}")

    @app.command("fix-status")
    def fix_status_command(
        session: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
        repo: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
        api_version: Annotated[str, typer.Option()] = "v3",
    ) -> None:
        """Read status of an existing session. This command never creates or retries one."""
        with checked():
            previous = read_model(session, FixResult)
            if previous.session_id is None or api_version not in {"v1", "v3"}:
                raise ValueError("An existing Devin session and supported API version are required")
            current = _devin(repo, api_version, 1).poll(previous.task_id, previous.session_id)
            write_model(session, current)
            typer.echo(f"Fixer status: {current.status}; PR: {current.pr_url or '<pending>'}")

    @app.command("verify")
    def verify_command(
        baseline: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
        inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
        task: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
            "data/fixes/demo/fix_task.json"
        ),
        repo: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
        tokenizer: Annotated[Path, typer.Option()] = Path("data/tokenizer"),
        quality_result: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
        quality_review: Annotated[
            list[Path] | None, typer.Option(exists=True, dir_okay=False)
        ] = None,
        out: Annotated[Path, typer.Option()] = Path("eval_results/verify.json"),
        rendered_out: Annotated[Path, typer.Option()] = Path("data/demo/requests_candidate.jsonl"),
        test_timeout: Annotated[int, typer.Option(min=1)] = 120,
    ) -> None:
        """Replay and check a candidate fix locally; never perform quality inference."""
        with checked():
            saved, _ = load_bundle(task)
            loaded = _tokenizer(tokenizer, saved.config)
            result, after, report = verify_bundle(
                repo=repo,
                task_path=task,
                report_path=baseline,
                input_path=inputs,
                tokenizer=loaded,
                quality_path=quality_result,
                review_paths=quality_review or [],
                test_timeout=test_timeout,
            )
            write_model(out, result)
            records = read_recorded(inputs)
            provenance = VerificationRun(
                timestamp=datetime.now(UTC).isoformat(),
                git_sha=snapshot(repo, saved.excluded_artifacts).git_sha,
                source_sha256=result.after_source_sha256,
                diff_sha256=result.diff_sha256,
                task_sha256=result.task_sha256,
                config_sha256=result.config_sha256,
                inputs_sha256=result.inputs_sha256,
                verify_sha256=file_sha(out),
                model=saved.config.vllm.model,
                revision=saved.config.vllm.revision,
                tokenizer=loaded.identity,
                vllm_version=saved.config.vllm.version,
                n_requests=len(records),
                seed={
                    key: sorted({record[key] for record in records})
                    for key in ("rng_seed", "worker_seed")
                },
            )
            write_model(out.with_suffix(".run.json"), provenance)
            if after:
                write_requests(after, rendered_out)
            if report is not None:
                write_model(out.with_suffix(".report.json"), report)
            typer.echo(
                f"Verification: {'passed' if result.passed else 'not approved'}; "
                f"quality: {result.quality_guard.status}. Result: {out}"
            )
            if not result.passed:
                raise typer.Exit(1)

    @app.command("review-quality")
    def review_command(
        result: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
        case: Annotated[str, typer.Option()],
        reviewer: Annotated[str, typer.Option()],
        reason: Annotated[str, typer.Option()],
        out: Annotated[Path, typer.Option()],
    ) -> None:
        """Record explicit human review of a changed synthetic output; cannot waive assertions."""
        with checked():
            run = read_model(result, QualityRun)
            output = next((o for o in run.outputs if o.id == case), None)
            if output is None:
                raise ValueError("Unknown golden case")
            if out.exists():
                raise ValueError("Review artifact already exists; use a new path")
            review = QualityReview(
                quality_result_sha256=file_sha(result),
                case_id=case,
                before_output_sha256=digest(output.before),
                after_output_sha256=digest(output.after),
                reviewer=reviewer,
                reason=reason,
                timestamp=datetime.now(UTC).isoformat(),
            )
            write_model(out, review)
            typer.echo(
                "Review recorded. The verifier still evaluates all assertions independently."
            )

    @app.command("approve")
    def approve_command(
        verify: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
        baseline: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
        inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
        reviewer: Annotated[str, typer.Option()],
        diff_sha256: Annotated[str, typer.Option()],
        task: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
            "data/fixes/demo/fix_task.json"
        ),
        repo: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
        tokenizer: Annotated[Path, typer.Option()] = Path("data/tokenizer"),
        quality_review: Annotated[
            list[Path] | None, typer.Option(exists=True, dir_okay=False)
        ] = None,
        out: Annotated[Path, typer.Option()] = Path("eval_results/approval.json"),
    ) -> None:
        """Human approval of the exact verified diff; revalidate current quality evidence."""
        with checked():
            original = read_model(verify, VerifyResult)
            saved, _ = load_bundle(task)
            source = snapshot(repo, saved.excluded_artifacts)
            if (
                original.after_source_sha256 != source.sha256
                or original.task_sha256 != digest(saved.task)
                or original.tests.command != saved.task.test_command
                or original.tests.output_sha256 is None
                or original.quality_result_path is None
            ):
                raise ValueError("Verification is stale or incomplete; rerun verify")
            loaded = _tokenizer(tokenizer, saved.config)
            quality_path = Path(original.quality_result_path)
            fresh, _, _ = verify_bundle(
                repo=repo,
                task_path=task,
                report_path=baseline,
                input_path=inputs,
                tokenizer=loaded,
                quality_path=quality_path,
                review_paths=quality_review or [],
                existing_tests=original.tests,
            )
            if fresh != original:
                raise ValueError("Current evidence differs from verify.json; rerun verify")
            approval = make_approval(
                fresh,
                current_source_sha256=source.sha256,
                expected_diff_sha256=diff_sha256,
                verify_sha256=file_sha(verify),
                quality_result_sha256=file_sha(quality_path),
                reviewer=reviewer,
                timestamp=datetime.now(UTC).isoformat(),
            )
            if out.exists():
                raise ValueError("Approval artifact already exists; use a new path")
            write_model(out, approval)
            typer.echo("Approval recorded for the exact verified diff. No PR was merged.")
