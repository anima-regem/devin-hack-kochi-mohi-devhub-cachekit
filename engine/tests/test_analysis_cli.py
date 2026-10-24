import hashlib
from pathlib import Path

from cachekit.cli import app
from cachekit.ingest.jsonl import write_requests
from cachekit.models import AnalysisRun, Report, RequestRecord
from typer.testing import CliRunner


def test_cli_writes_valid_provenance_and_repeatable_report(tmp_path, qwen_tokenizer):
    logs = tmp_path / "requests.jsonl"
    write_requests(
        [
            RequestRecord(
                id=str(i),
                ts=i,
                messages=[{"role": "user", "content": "hello"}],
                meta={"source": "synthetic-cli-test", "seed": 42},
            )
            for i in range(2)
        ],
        logs,
    )
    tokenizer = Path(__file__).resolve().parents[2] / "data" / "tokenizer"
    out = tmp_path / "report.json"
    args = ["analyze", str(logs), "--tokenizer", str(tokenizer), "--out", str(out)]
    runner = CliRunner()
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert "SIMULATED" in first.output
    payload = out.read_bytes()
    report = Report.model_validate_json(payload)
    metadata = AnalysisRun.model_validate_json(out.with_suffix(".run.json").read_bytes())
    assert metadata.report_sha256 == hashlib.sha256(payload).hexdigest()
    assert metadata.input_sha256 == hashlib.sha256(logs.read_bytes()).hexdigest()
    assert metadata.config_sha256 == report.config_sha256
    assert metadata.seed["seed"] == [42]
    assert metadata.gpu is None
    assert report.backends[0].cost_actual is None
    assert runner.invoke(app, args).exit_code == 0
    assert out.read_bytes() == payload


def test_cli_rejects_unimplemented_profile_and_withholds_invalid_log_content(tmp_path):
    logs = tmp_path / "requests.jsonl"
    logs.write_text('{"messages": "PRIVATE_SENTINEL"}\n')
    runner = CliRunner()
    failed = runner.invoke(app, ["analyze", str(logs), "--tokenizer", str(tmp_path)])
    assert failed.exit_code == 1
    assert "PRIVATE_SENTINEL" not in failed.output
    assert "line 1; input content withheld" in failed.output
    failed = runner.invoke(
        app,
        [
            "analyze",
            str(logs),
            "--tokenizer",
            str(tmp_path),
            "--backends",
            "openai",
        ],
    )
    assert failed.exit_code == 1
    assert "Only the vLLM profile" in failed.output
