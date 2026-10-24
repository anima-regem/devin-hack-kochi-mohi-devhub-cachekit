"""Export reviewed synthetic views, never arbitrary API uploads or raw inputs."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT)]

from cachekit.api_models import BenchView  # noqa: E402
from cachekit.ingest.config import load_config  # noqa: E402
from cachekit.ingest.fix_workflow import load_bundle  # noqa: E402
from cachekit.ingest.workspace import Workspace  # noqa: E402


def main():
    workspace = Workspace(ROOT, ROOT / "data/tokenizer", load_config())
    report = workspace.bundle("demo-before")
    if report.metadata.dataset != ["synthetic-helpdesk"] or report.report.routes != [
        "helpdesk.answer"
    ]:
        raise ValueError("Only the reviewed public synthetic helpdesk report can be exported")
    task = None
    path = ROOT / "data/fixes/demo/fix_task.json"
    if path.is_file():
        task = workspace.task_view(load_bundle(path)[0].task.id)
    output = {
        "report": report.model_dump(mode="json"),
        "fix": task.model_dump(mode="json") if task else None,
        "bench": BenchView.model_validate(workspace.bench()).model_dump(mode="json"),
    }
    # Raw baselines, dataset reports and GPU log tails are deliberately omitted.
    path = ROOT / "web/public/demo/workspace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )
    print("Exported reviewed synthetic report, redacted task status and measured smoke counters.")


if __name__ == "__main__":
    main()
