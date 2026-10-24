"""Pure task generation. Never export template previews, logs, or arbitrary evidence."""

import hashlib
import re
from pathlib import PurePosixPath

from cachekit.fix.models import FixTask, GenerationConfig, TaskFinding
from cachekit.models import Report
from cachekit.serialization import canonical_json

REPO_URL = "https://github.com/mohi-devhub/cachekit"


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def safe_relative(path: str) -> str:
    item = PurePosixPath(path)
    if item.is_absolute() or not item.parts or any(p in {"..", "."} for p in item.parts):
        raise ValueError("Expected an explicit repository-relative file path")
    if any(p.startswith(".") or p in {"data", "eval_results", "node_modules"} for p in item.parts):
        raise ValueError("Private, hidden, generated and dependency files cannot be fix targets")
    if "\\" in path or "\n" in path:
        raise ValueError("Unsupported file path")
    return item.as_posix()


def make_task(
    report: Report,
    *,
    report_sha256: str,
    before_source_sha256: str,
    golden_suite_sha256: str,
    allowed_files: list[str],
    test_command: list[str],
    generation: GenerationConfig,
    finding_ids: list[str] | None = None,
) -> FixTask:
    selected = [f for f in report.findings if finding_ids is None or f.id in finding_ids]
    if not selected or (finding_ids and set(finding_ids) != {f.id for f in selected}):
        raise ValueError("Select existing findings; a task must contain at least one finding")
    backend = next((b for b in report.backends if b.backend == "vllm"), None)
    if backend is None:
        raise ValueError("A vLLM baseline is required")
    # Breaker names are a finite engine vocabulary. Untrusted report strings stay local.
    from cachekit.analyze.classify import HINTS

    if any(f.breaker not in HINTS for f in selected):
        raise ValueError("Unrecognized breaker type")
    if any(re.fullmatch(r"[a-f0-9]{24}", f.id) is None for f in selected):
        raise ValueError("Finding IDs must be engine-generated opaque identifiers")
    fields = dict(
        repo_url=REPO_URL,
        report_sha256=report_sha256,
        input_sha256=report.input_sha256,
        config_sha256=report.config_sha256,
        before_source_sha256=before_source_sha256,
        golden_suite_sha256=golden_suite_sha256,
        quality_generation=generation,
        findings=[
            TaskFinding(
                id=f.id,
                breaker=f.breaker,
                severity=f.severity,
                first_divergence_token=f.first_divergence_token,
                stable_tokens_after=f.stable_tokens_after,
                requests_affected=f.requests_affected,
                review_required=not f.safe_to_move,
            )
            for f in sorted(selected, key=lambda f: f.id)
        ],
        # Route labels can contain tenant/user identifiers. Export opaque route hashes.
        routes=["route-" + digest(route)[:16] for route in sorted({f.route for f in selected})],
        target_hit_rate=backend.achievable_hit_rate,
        allowed_files=sorted({safe_relative(p) for p in allowed_files}),
        test_command=test_command,
    )
    candidate = FixTask(id="pending", **fields)
    return candidate.model_copy(
        update={"id": digest(candidate.model_dump(mode="json", exclude={"id"}))[:24]}
    )


def task_markdown(task: FixTask) -> str:
    lines = [
        f"# Fix task {task.id}: improve prompt-cache reuse",
        "",
        f"Repository: {task.repo_url}",
        f"Create branch `fix/cachekit-{task.id}` and open a PR. Do not merge it.",
        "",
        "## Findings (redacted; source locations are not inferred)",
    ]
    for finding in task.findings:
        review = "; requires semantic review" if finding.review_required else ""
        lines.append(
            f"- [{finding.severity}] {finding.breaker}: divergence at token "
            f"{finding.first_divergence_token}; {finding.stable_tokens_after} stable tokens "
            f"downstream; {finding.requests_affected} requests affected{review}."
        )
    lines += [
        "",
        "## Required changes",
        "- Refactor the application source; keep the prompt builder's public signature unchanged.",
        "- Keep static policies/instructions first and tool ordering deterministic.",
        "- Put eligible changing context after static content; preserve values and instructions.",
        "- Keep selected examples and their text; do not replace them with a different fixed set.",
        "- Preserve conversation roles, tool definitions, authorization and generation settings.",
        "- Moving system context into user messages is a semantic change requiring quality review.",
        "- Personalization, locale, tool availability and history changes require review.",
        "- Do not broaden tools, delete history, reword instructions or weaken tests for a target.",
        "- Log choices in DECISIONS.md when allowed, before collecting quality evidence.",
        "",
        "## Acceptance criteria",
        f"- Recorded-input simulated vLLM hit rate >= {task.target_hit_rate:.17g}.",
        "- No high-severity findings remain for the selected breaker types.",
        "- Normalized content and all dynamic values are preserved; tool multisets are identical.",
        "- Repository tests pass: `" + " ".join(task.test_command) + "`.",
        "- Only these files may change:",
        *[f"  - `{path}`" for path in task.allowed_files],
        "- Five fixed golden cases have actual current BEFORE/AFTER evidence. All AFTER assertions",
        "  pass; truncated outputs fail; changed outputs require explicit human review.",
        "- Missing or stale quality evidence is incomplete, never a pass. Keep the PR unapproved.",
        "- Mohith verifies locally/on Modal and approves the exact verified diff hash.",
        "",
        "## Privacy and handoff",
        "- Raw request logs, recorded private inputs and responses stay local or on Modal.",
        "- Do not read .env or credentials, upload data/, or call an external LLM with logs.",
        "- Keep docs/, private agent notes, CLAUDE.md and DECISIONS.md local; do not commit them.",
        "- Preserve organizer files; update CHANGELOG.md and AI_USAGE.md with honest timestamps.",
        "- Report the branch/PR URL, changed files and actual checks. Do not invent results.",
        "- No source locator evidence exists yet; inspect the allowed builder source in the repo.",
        "- The reuse target is a simulation, not a measured latency or dollar-savings claim.",
        "",
    ]
    return "\n".join(lines)
