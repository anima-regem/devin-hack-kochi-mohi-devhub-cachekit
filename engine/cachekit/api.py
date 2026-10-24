"""Local workspace API. Analysis and verification never invoke inference."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cachekit import __version__
from cachekit.api_models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ApproveRequest,
    BenchView,
    DatasetOption,
    ReportBundle,
    ReportSummary,
    TaskRequest,
    TaskView,
    VerifyRequest,
    VerifyResponse,
)
from cachekit.fix.models import Approval, VerificationRun, VerifyResult
from cachekit.ingest.config import load_config
from cachekit.ingest.fix import file_sha, read_model, read_recorded, snapshot, write_model
from cachekit.ingest.fix_workflow import approve_current, load_bundle, verify_bundle
from cachekit.ingest.jsonl import write_requests
from cachekit.ingest.workspace import DATASETS, Workspace
from cachekit.models import BoundaryModel, Report


class HealthResponse(BoundaryModel):
    status: Literal["ok"] = "ok"
    version: str


def create_app(
    repo: Path | None = None,
    tokenizer: Path | None = None,
    config=None,
    max_upload_bytes: int = 10 * 1024 * 1024,
) -> FastAPI:
    root = (repo or Path.cwd()).resolve()
    workspace = Workspace(root, tokenizer or root / "data/tokenizer", config or load_config())
    api = FastAPI(title="cachekit", version=__version__)
    api.state.workspace = workspace
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse(status_code=422, content={"detail": "Invalid request parameters."})

    @api.exception_handler(ValueError)
    async def invalid_data(request, error):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "The local input or evidence could not be validated. "
                "Check format, source identity, "
                "tokenizer and context limits. No input content was returned."
            },
        )

    @api.exception_handler(FileNotFoundError)
    async def missing_data(request, error):
        return JSONResponse(
            status_code=404, content={"detail": "The local artifact is unavailable."}
        )

    @api.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(version=__version__)

    @api.get("/datasets", response_model=list[DatasetOption])
    def datasets():
        return workspace.datasets()

    @api.get("/reports", response_model=list[ReportSummary])
    def reports():
        return workspace.reports()

    @api.get("/reports/{report_id}", response_model=Report)
    def report(report_id: str):
        return workspace.bundle(report_id).report

    @api.get("/reports/{report_id}/bundle", response_model=ReportBundle)
    def report_bundle(report_id: str):
        return workspace.bundle(report_id)

    @api.post("/analyze", response_model=AnalyzeResponse)
    def analyze_dataset(options: AnalyzeRequest):
        path = root / DATASETS[options.dataset_id][1]
        if not path.is_file():
            raise FileNotFoundError()
        if path.stat().st_size > max_upload_bytes:
            raise HTTPException(413, "This local sample exceeds the configured input limit.")
        return {"report_id": workspace.analyze_bytes(path.read_bytes(), options.dataset_id)}

    @api.post("/analyze/upload", response_model=AnalyzeResponse)
    async def analyze_upload(request: Request):
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > max_upload_bytes:
                raise HTTPException(413, "The file exceeds the upload limit. Use a smaller log.")
            content.extend(chunk)
        report_id = await run_in_threadpool(
            workspace.analyze_bytes, bytes(content), "uploaded-jsonl"
        )
        return {"report_id": report_id}

    @api.post("/reports/{report_id}/task", response_model=TaskView)
    def task(report_id: str, options: TaskRequest):
        return workspace.create_task(report_id, options.finding_ids)

    @api.post("/reports/{report_id}/findings/{finding_id}/task", response_model=TaskView)
    def finding_task(report_id: str, finding_id: str):
        return workspace.create_task(report_id, [finding_id])

    @api.get("/fix/{task_id}", response_model=TaskView)
    def task_view(task_id: str):
        return workspace.task_view(task_id)

    @api.post("/verify", response_model=VerifyResponse)
    def verify(options: VerifyRequest):
        task_path = workspace.task_path(options.task_id)
        directory = task_path.parent
        report_path = workspace.results / "task-reports" / f"{options.task_id}.json"
        if not report_path.is_file():
            raise HTTPException(409, "Create a current task from its report before verification.")
        result, after, candidate = verify_bundle(
            repo=root,
            task_path=task_path,
            report_path=report_path,
            input_path=directory / "recorded_inputs.jsonl",
            tokenizer=workspace.tokenizer(),
            quality_path=workspace.evidence_path("quality", options.quality_run_id)
            if options.quality_run_id
            else None,
            review_paths=[workspace.evidence_path("review", key) for key in options.review_ids],
        )
        out = workspace.results / "verifications" / f"{options.task_id}.latest.json"
        write_model(out, result)
        verification_id = file_sha(out)
        write_model(out.parent / f"{verification_id}.json", result)
        baseline, _ = load_bundle(task_path)
        records = read_recorded(directory / "recorded_inputs.jsonl")
        provenance = VerificationRun(
            timestamp=datetime.now(UTC).isoformat(),
            git_sha=snapshot(root, baseline.excluded_artifacts).git_sha,
            source_sha256=result.after_source_sha256,
            diff_sha256=result.diff_sha256,
            task_sha256=result.task_sha256,
            config_sha256=result.config_sha256,
            inputs_sha256=result.inputs_sha256,
            verify_sha256=verification_id,
            model=baseline.config.vllm.model,
            revision=baseline.config.vllm.revision,
            tokenizer=workspace.tokenizer().identity,
            vllm_version=baseline.config.vllm.version,
            n_requests=len(records),
            seed={key: sorted({r[key] for r in records}) for key in ("rng_seed", "worker_seed")},
        )
        write_model(out.parent / f"{verification_id}.run.json", provenance)
        if candidate is not None:
            write_model(workspace.results / "candidates" / f"{options.task_id}.json", candidate)
        if after:
            write_requests(after, workspace.private / "candidates" / f"{options.task_id}.jsonl")
        return VerifyResponse(id=verification_id, result=result)

    @api.post("/approve", response_model=Approval)
    def approve(options: ApproveRequest):
        task_path = workspace.task_path(options.task_id)
        verification_path = workspace.results / "verifications" / f"{options.verification_id}.json"
        if (
            not verification_path.is_file()
            or file_sha(verification_path) != options.verification_id
        ):
            raise FileNotFoundError()
        saved = read_model(verification_path, VerifyResult)
        if saved.task_id != options.task_id:
            raise HTTPException(409, "Verification belongs to a different task.")
        approval = approve_current(
            repo=root,
            task_path=task_path,
            report_path=workspace.results / "task-reports" / f"{options.task_id}.json",
            input_path=task_path.parent / "recorded_inputs.jsonl",
            verification_path=verification_path,
            tokenizer=workspace.tokenizer(),
            review_paths=[workspace.evidence_path("review", key) for key in options.review_ids],
            reviewer=options.reviewer,
            expected_diff_sha256=options.diff_sha256,
            timestamp=datetime.now(UTC).isoformat(),
        )
        write_model(
            workspace.results / "approvals" / f"{file_sha(verification_path)}.json", approval
        )
        return approval

    @api.get("/bench", response_model=BenchView)
    def bench():
        return workspace.bench()

    return api


app = create_app()
