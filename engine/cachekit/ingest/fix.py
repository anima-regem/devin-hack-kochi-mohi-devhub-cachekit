"""Local source identity, subprocess replay, and repository test I/O."""

import ast
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from cachekit.fix.models import RenderBatch, RenderResult, SourceFile, SourceSnapshot, TestResult
from cachekit.fix.task import digest
from cachekit.models import BoundaryModel, RequestRecord
from cachekit.serialization import canonical_json

SKIP_DIRS = {
    "data",
    "eval_results",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".next",
    ".venv",
    ".git",
    ".cache",
    ".tools",
    ".pytest_cache",
    ".ruff_cache",
}
ENGINE_ROOT = Path(__file__).resolve().parents[2]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_model(path: Path, model):
    try:
        return model.model_validate_json(path.read_bytes())
    except Exception:
        raise ValueError(f"Invalid {model.__name__}; file contents withheld") from None


def write_model(path: Path, value: BoundaryModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def snapshot(repo: Path, excluded: list[str] | tuple[str, ...] = ()) -> SourceSnapshot:
    root = repo.resolve(strict=True)
    files: dict[str, SourceFile] = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in SKIP_DIRS
            and (not d.startswith(".") or d == ".github")
            and not d.endswith(".egg-info")
        )
        for directory_name in dirs:
            if (Path(directory) / directory_name).is_symlink():
                raise ValueError("Source directory symlinks are unsupported")
        for name in sorted(names):
            if name.startswith(".") and name not in {".gitignore", ".env.example"}:
                continue
            if name.endswith((".pyc", ".tsbuildinfo", ".pem", ".key")):
                continue
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative in excluded:
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Source symlinks and special files are unsupported")
            if info.st_size > 2 * 1024 * 1024:
                raise ValueError("An unaudited large file is outside the ignored data directories")
            files[relative] = SourceFile(
                sha256=file_sha(path), executable=bool(info.st_mode & 0o111)
            )
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return SourceSnapshot(
        files=files,
        sha256=digest({k: v.model_dump() for k, v in files.items()}),
        git_sha=git.stdout.strip() if git.returncode == 0 else None,
    )


def changes(before: SourceSnapshot, after: SourceSnapshot) -> tuple[list[str], str]:
    paths = sorted(
        k for k in set(before.files) | set(after.files) if before.files.get(k) != after.files.get(k)
    )
    identity = digest(
        {
            "before_source_sha256": before.sha256,
            "after_source_sha256": after.sha256,
            "changes": {
                k: {
                    "before": before.files[k].model_dump() if k in before.files else None,
                    "after": after.files[k].model_dump() if k in after.files else None,
                }
                for k in paths
            },
        }
    )
    return paths, identity


def builder_signature(repo: Path) -> str:
    path = repo / "demo_app" / "helpdesk" / "prompt.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = [
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_request"
        ]
        if len(functions) != 1:
            raise ValueError("Builder must have one top-level build_request function")
        function = functions[0]
        return digest(
            {
                "args": ast.dump(function.args),
                "returns": ast.dump(function.returns) if function.returns else None,
            }
        )
    except (SyntaxError, OSError):
        raise ValueError("Cannot validate the prompt builder signature; source withheld") from None


def read_recorded(path: Path) -> list[dict]:
    # Demo adapter is explicit; other apps need their own replay adapter or fresh capture.
    from demo_app.helpdesk.models import RecordedInput

    try:
        records = [
            RecordedInput.model_validate_json(line).model_dump(mode="json")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not records or len({r["id"] for r in records}) != len(records):
            raise ValueError("Recorded inputs must be nonempty with unique IDs")
        return records
    except Exception:
        raise ValueError("Invalid recorded demo inputs; contents withheld") from None


def render_in_repo(repo: Path, records: list[dict]) -> list[RequestRecord]:
    batches: dict[int, list[dict]] = {}
    for record in records:
        batches.setdefault(record["worker_seed"], []).append(record)
    output: list[RequestRecord] = []
    with tempfile.TemporaryDirectory(prefix="cachekit-replay-") as scratch:
        for seed, batch in sorted(batches.items()):
            env = os.environ.copy()
            env.update(
                PYTHONHASHSEED=str(seed),
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONPYCACHEPREFIX=scratch,
                PYTHONPATH=str(ENGINE_ROOT),
            )
            payload = RenderBatch(repo=str(repo.resolve()), records=batch)
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "cachekit.ingest.replay_worker"],
                input=canonical_json(payload),
                cwd=repo,
                env=env,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if completed.returncode:
                raise ValueError("Patched builder replay failed; subprocess output withheld")
            try:
                output.extend(RenderResult.model_validate_json(completed.stdout).requests)
            except Exception:
                raise ValueError("Invalid builder replay output; contents withheld") from None
    return sorted(output, key=lambda r: (r.ts, r.id))


def run_tests(repo: Path, command: list[str], *, timeout: int = 120) -> TestResult:
    env = os.environ.copy()
    env.update(
        PYTHONPATH=os.pathsep.join((str(repo / "engine"), str(repo))), PYTHONDONTWRITEBYTECODE="1"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="cachekit-tests-") as scratch:
            env["PYTHONPYCACHEPREFIX"] = scratch
            result = subprocess.run(
                command, cwd=repo, env=env, capture_output=True, timeout=timeout, check=False
            )
    except subprocess.TimeoutExpired:
        return TestResult(status="timeout", command=command, exit_code=None)
    except OSError:
        return TestResult(status="failed", command=command, exit_code=None)
    return TestResult(
        status="passed" if result.returncode == 0 else "failed",
        command=command,
        exit_code=result.returncode,
        output_sha256=hashlib.sha256(result.stdout + b"\0" + result.stderr).hexdigest(),
    )
