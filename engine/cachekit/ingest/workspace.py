"""Bounded local workspace persistence for the API and public synthetic export."""

import hashlib
import json
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from cachekit.api_models import DatasetOption, ReportBundle, ReportSummary, TaskView
from cachekit.fix.models import FixResult, QualityReview, QualityRun, VerifyResult
from cachekit.fix.task import task_markdown
from cachekit.ingest.fix import changes, file_sha, read_model, snapshot, write_model
from cachekit.ingest.fix_workflow import default_allowed_files, load_bundle, prepare_task
from cachekit.ingest.jsonl import parse_requests
from cachekit.ingest.tokenizer import load_tokenizer
from cachekit.models import AnalysisRun, Report
from cachekit.report import analyze
from cachekit.serialization import canonical_json
from cachekit.settings import RunConfig

DATASETS = {
    "demo-before": (
        "Fictional helpdesk · BEFORE",
        "data/demo/requests_before.jsonl",
        "Controlled synthetic traffic with planted cache breakers.",
    ),
    "glaive-sample": (
        "Glaive · local sample",
        "data/converted/glaive_requests.jsonl",
        "Local function-calling dataset conversion; synthetic arrivals.",
    ),
    "swe-sample": (
        "SWE-agent · short local sample",
        "data/converted/swe_short_sample.jsonl",
        "Explicitly limited trajectory sample within the context budget.",
    ),
}


class Workspace:
    def __init__(self, repo: Path, tokenizer: Path, config: RunConfig):
        self.repo, self.tokenizer_path, self.config = repo.resolve(), tokenizer.resolve(), config
        self.results = self.repo / "eval_results/local"
        self.private = self.repo / "data/api"
        self.lock = RLock()
        self._tokenizer = None

    def tokenizer(self):
        with self.lock:
            if self._tokenizer is None:
                self._tokenizer = load_tokenizer(
                    self.tokenizer_path,
                    model=self.config.vllm.model,
                    revision=self.config.vllm.revision,
                )
            return self._tokenizer

    def datasets(self) -> list[DatasetOption]:
        return [
            DatasetOption(
                id=key, name=name, available=(self.repo / path).is_file(), description=description
            )
            for key, (name, path, description) in DATASETS.items()
        ]

    def bundle(self, report_id: str) -> ReportBundle:
        if report_id == "demo-before":
            path = self.repo / "eval_results/demo_before_report.json"
        elif re.fullmatch(r"[a-f0-9]{64}", report_id):
            path = self.results / "reports" / f"{report_id}.json"
        else:
            raise FileNotFoundError("Unknown report")
        if not path.is_file():
            raise FileNotFoundError("Unknown report")
        report = read_model(path, Report)
        metadata = read_model(path.with_suffix(".run.json"), AnalysisRun)
        if (
            file_sha(path) != metadata.report_sha256
            or report.config_sha256 != metadata.config_sha256
            or report.input_sha256 != metadata.input_sha256
            or report.n_requests != metadata.n_requests
        ):
            raise ValueError("Report provenance checksum mismatch")
        return ReportBundle(id=report_id, report=report, metadata=metadata)

    def report_path(self, report_id: str) -> Path:
        self.bundle(report_id)
        if report_id == "demo-before":
            return self.repo / "eval_results/demo_before_report.json"
        return self.results / "reports" / f"{report_id}.json"

    def reports(self) -> list[ReportSummary]:
        ids = ["demo-before"]
        directory = self.results / "reports"
        if directory.exists():
            ids += [
                p.stem for p in directory.glob("*.json") if re.fullmatch(r"[a-f0-9]{64}", p.stem)
            ]
        result = []
        for key in ids:
            try:
                bundle = self.bundle(key)
            except (ValueError, OSError):
                continue
            result.append(
                ReportSummary(
                    id=key,
                    n_requests=bundle.report.n_requests,
                    n_findings=len(bundle.report.findings),
                    routes=bundle.report.routes,
                    timestamp=bundle.metadata.timestamp,
                )
            )
        return sorted(result, key=lambda r: (r.timestamp, r.id), reverse=True)

    def analyze_bytes(self, raw: bytes, label: str) -> str:
        records, input_hash = parse_requests(raw)
        if not records:
            raise ValueError("The request log is empty")
        tokenizer = self.tokenizer()
        report = analyze(records, self.config, tokenizer, input_sha256=input_hash)
        payload = (canonical_json(report) + "\n").encode()
        report_id = hashlib.sha256(payload).hexdigest()
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True, check=False
        )
        metadata = AnalysisRun(
            timestamp=datetime.now(UTC).isoformat(),
            git_sha=git.stdout.strip() if git.returncode == 0 else None,
            git_sha_note=None if git.returncode == 0 else "No available repository commit",
            git_dirty=bool(
                subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=self.repo,
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
            )
            if git.returncode == 0
            else None,
            dataset=[label],
            seed={
                key: sorted({int(r.meta[key]) for r in records if key in r.meta})
                for key in ("seed", "rng_seed", "worker_seed")
            },
            n_requests=len(records),
            input_sha256=input_hash,
            config_sha256=report.config_sha256,
            report_sha256=report_id,
            model=self.config.vllm.model,
            tokenizer=tokenizer.identity,
            vllm_version=self.config.vllm.version,
            block_size=self.config.vllm.block_size,
            kv_capacity_tokens=self.config.vllm.capacity_blocks * self.config.vllm.block_size,
            note="Local API CPU simulation. Private inputs/artifacts are not public demo exports.",
        )
        with self.lock:
            inputs = self.private / "inputs" / f"{input_hash}.jsonl"
            inputs.parent.mkdir(parents=True, exist_ok=True)
            inputs.write_bytes(raw)
            out = self.results / "reports" / f"{report_id}.json"
            if not out.exists():
                write_model(out.with_suffix(".run.json"), metadata)
                out.write_bytes(payload)
        return report_id

    def create_task(self, report_id: str, finding_ids: list[str] | None) -> TaskView:
        bundle = self.bundle(report_id)
        demo_path = self.repo / DATASETS["demo-before"][1]
        if not demo_path.is_file() or file_sha(demo_path) != bundle.report.input_sha256:
            raise ValueError("Task replay currently requires the recorded helpdesk demo inputs")
        from cachekit.fix.models import GenerationConfig

        with self.lock:
            temporary = self.private / "tasks" / ("pending-" + uuid.uuid4().hex)
            baseline = prepare_task(
                repo=self.repo,
                report_path=self.report_path(report_id),
                input_path=self.repo / "data/demo/inputs.jsonl",
                before_path=demo_path,
                suite_path=self.repo / "demo_app/goldens.json",
                bundle=temporary,
                config=self.config,
                tokenizer=self.tokenizer(),
                allowed_files=default_allowed_files(self.repo),
                test_command=["python3", "-m", "pytest", "-q"],
                finding_ids=finding_ids,
                generation=GenerationConfig(),
            )
            write_model(temporary / "fix_task.json", baseline.task)
            write_model(temporary / "fix_baseline.json", baseline)
            (temporary / "fix_task.md").write_text(task_markdown(baseline.task), encoding="utf-8")
            destination = self.private / "tasks" / baseline.task.id
            if destination.exists():
                import shutil

                shutil.rmtree(temporary)
            else:
                temporary.rename(destination)
            copy = self.results / "task-reports" / f"{baseline.task.id}.json"
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(self.report_path(report_id).read_bytes())
            return self.task_view(baseline.task.id)

    def task_path(self, task_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{24}", task_id):
            raise FileNotFoundError("Unknown task")
        generated = self.private / "tasks" / task_id / "fix_task.json"
        if generated.is_file():
            return generated
        historical = self.repo / "data/fixes/demo/fix_task.json"
        if historical.is_file() and load_bundle(historical)[0].task.id == task_id:
            return historical
        raise FileNotFoundError("Unknown task")

    def task_view(self, task_id: str) -> TaskView:
        path = self.task_path(task_id)
        baseline, suite = load_bundle(path)
        current = snapshot(self.repo, baseline.excluded_artifacts)
        changed, _ = changes(baseline.source, current)
        state = (
            "stale"
            if set(changed) - set(baseline.task.allowed_files)
            else ("candidate" if changed else "prepared")
        )
        verification = None
        for p in [
            self.results / "verifications" / f"{task_id}.latest.json",
            self.repo / "eval_results/phase3_verify.json",
        ]:
            if p.is_file():
                result = read_model(p, VerifyResult)
                if result.task_id == task_id:
                    verification = result
                    break
        handoff = None
        p = self.repo / "eval_results/fix_handoff.json"
        if p.is_file():
            saved = read_model(p, FixResult)
            if saved.task_id == task_id:
                handoff = saved.model_dump(mode="json")
        return TaskView(
            task=baseline.task,
            markdown=task_markdown(baseline.task),
            state=state,
            verification=verification,
            verification_current=bool(
                verification and verification.after_source_sha256 == current.sha256
            ),
            handoff=handoff,
            golden_cases=[
                {
                    "id": c.id,
                    "category": c.category,
                    "assertions": [a.id for a in c.assertions],
                    "expects_json": c.output_json_schema is not None,
                }
                for c in suite.cases
            ],
            note=(
                "Actual golden inference and an authoritative current verification "
                "are required for approval."
            ),
        )

    def evidence_path(self, kind: str, evidence_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", evidence_id):
            raise FileNotFoundError("Unknown evidence")
        model = QualityRun if kind == "quality" else QualityReview
        for path in (self.repo / "eval_results/quality_guard").rglob("*.json"):
            if file_sha(path) == evidence_id:
                read_model(path, model)
                return path
        raise FileNotFoundError("Unknown evidence")

    def bench(self) -> dict:
        path = self.repo / "eval_results/modal_smoke.json"
        if not path.is_file():
            return {
                "smoke": None,
                "benchmarks": [],
                "note": "No measured benchmark run is available.",
            }
        raw = json.loads(path.read_text())
        summary = raw["summary"]
        return {
            "smoke": {
                "experiment": "serving_smoke",
                "status": raw["status"],
                "model": raw["model"],
                "revision": raw["model_revision"],
                "gpu": raw["gpu_type_requested"],
                "vllm_version": raw["vllm_version"],
                "timestamp": raw["finished_at"],
                "block_size": summary["block_size"],
                "capacity_tokens": summary["kv_cache_size_tokens"],
                "requests": [
                    {
                        "request": r["request"],
                        "prompt_tokens": r["prompt_tokens"],
                        "cached_tokens": summary["hits_delta_per_request"][i],
                        "queried_tokens": summary["queries_delta_per_request"][i],
                    }
                    for i, r in enumerate(raw["requests"])
                ],
                "source": "eval_results/modal_smoke.json",
                "sha256": file_sha(path),
            },
            "benchmarks": [],
            "note": "Serving validation only; no measured BEFORE/AFTER speedup or cost savings.",
        }
