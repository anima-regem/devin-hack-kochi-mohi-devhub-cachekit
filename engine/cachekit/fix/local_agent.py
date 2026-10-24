"""Prepared local handoff; never silently invokes another coding agent."""

from pathlib import Path

from cachekit.fix.models import FixResult, FixTask


class LocalAgentFixer:
    def run(self, task: FixTask, repo: Path) -> FixResult:
        return FixResult(
            task_id=task.id,
            status="prepared",
            branch=f"fix/cachekit-{task.id}",
            log=[
                "Give Codex/Claude only the generated redacted fix_task.md and repository source.",
                "Create the named branch, edit allowed files, run repository tests and open a PR.",
                "Private inputs and quality inference remain local/on Modal; approval is separate.",
            ],
        )
