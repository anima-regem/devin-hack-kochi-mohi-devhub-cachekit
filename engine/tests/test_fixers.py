from pathlib import Path

import httpx
import pytest
from cachekit.fix.devin import DevinFixer
from cachekit.fix.local_agent import LocalAgentFixer
from cachekit.fix.models import FixTask, GenerationConfig, TaskFinding
from pydantic import SecretStr


@pytest.fixture
def task():
    return FixTask(
        id="a" * 24,
        repo_url="https://github.com/mohi-devhub/cachekit",
        report_sha256="a" * 64,
        input_sha256="b" * 64,
        config_sha256="c" * 64,
        before_source_sha256="d" * 64,
        golden_suite_sha256="e" * 64,
        quality_generation=GenerationConfig(),
        routes=["route-opaque"],
        target_hit_rate=0.5,
        allowed_files=["demo_app/helpdesk/prompt.py"],
        test_command=["python3", "-m", "pytest"],
        findings=[
            TaskFinding(
                id="f" * 24,
                breaker="timestamp",
                severity="high",
                first_divergence_token=1,
                stable_tokens_after=1000,
                requests_affected=2,
                review_required=False,
            )
        ],
    )


def test_local_handoff_starts_nothing(task):
    result = LocalAgentFixer().run(task, Path("."))
    assert result.status == "prepared" and result.pr_url is None and result.session_id is None


@pytest.mark.parametrize("version", ["v1", "v3"])
def test_devin_explicit_approval_body_status_and_pr_collection(task, version):
    requests = []

    def handler(request):
        import json

        requests.append(request)
        assert request.headers["Authorization"] == "Bearer UNIT_TEST_SECRET"
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["max_acu_limit"] == 2
            assert body["secret_ids"] == [] and body["knowledge_ids"] == []
            assert "template_preview" not in body["prompt"]
            if version == "v3":
                assert body["repos"] == [task.repo_url]
                assert body["resumable"] is False
            return httpx.Response(
                200, json={"session_id": "devin-test", "url": "https://app.devin.ai/test"}
            )
        return httpx.Response(
            200,
            json={
                "session_id": "devin-test",
                "status": "exit",
                "pull_request": {"url": "https://github.com/mohi-devhub/cachekit/pull/7"},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fixer = DevinFixer(
            token=SecretStr("UNIT_TEST_SECRET"),
            api_version=version,
            max_acu_limit=2,
            org_id="org-test",
            client=client,
        )
        with pytest.raises(ValueError, match="explicitly approve"):
            fixer.run(task, Path("."))
        assert requests == []
        created = fixer.run(task, Path("."), approved=True)
        final = fixer.poll(task.id, created.session_id)
    assert final.status == "finished" and final.pr_url.endswith("/pull/7")
    assert "UNIT_TEST_SECRET" not in final.model_dump_json()
    assert len(requests) == 2


def test_failed_session_creation_is_not_retried_and_response_body_is_withheld(task):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403, text="UNIT_TEST_SECRET private diagnostic body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fixer = DevinFixer(
            token=SecretStr("UNIT_TEST_SECRET"), api_version="v1", max_acu_limit=2, client=client
        )
        with pytest.raises(ValueError) as error:
            fixer.run(task, Path("."), approved=True)
    assert len(calls) == 1 and "HTTP 403" in str(error.value)
    assert "UNIT_TEST_SECRET" not in str(error.value)
