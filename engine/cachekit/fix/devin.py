"""Explicitly authorized external fixer. No analysis imports this network client.

API contracts checked on 2026-10-24:
https://docs.devin.ai/api-reference/v1/sessions/create-a-new-devin-session
https://docs.devin.ai/api-reference/v3/sessions/post-organizations-sessions
https://docs.devin.ai/api-reference/v3/sessions/get-organizations-session
"""

from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from cachekit.fix.models import FixResult, FixTask
from cachekit.fix.task import task_markdown
from cachekit.models import BoundaryModel


class CreateV1(BoundaryModel):
    prompt: str
    max_acu_limit: int = Field(gt=0)
    idempotent: Literal[True] = True
    knowledge_ids: list[str] = Field(default_factory=list)
    secret_ids: list[str] = Field(default_factory=list)


class CreateV3(BoundaryModel):
    prompt: str
    max_acu_limit: int = Field(gt=0)
    repos: list[str]
    knowledge_ids: list[str] = Field(default_factory=list)
    secret_ids: list[str] = Field(default_factory=list)
    resumable: Literal[False] = False


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str | None = None
    pr_url: str | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str
    url: str | None = None
    status: str = "new"
    status_enum: str | None = None
    pull_request: PullRequest | None = None
    pull_requests: list[PullRequest] = Field(default_factory=list)


class DevinFixer:
    def __init__(
        self,
        *,
        token: SecretStr,
        api_version: Literal["v1", "v3"],
        max_acu_limit: int,
        org_id: str | None = None,
        client: httpx.Client | None = None,
    ):
        if max_acu_limit < 1:
            raise ValueError("An explicit positive ACU limit is required")
        if api_version == "v3" and not org_id:
            raise ValueError("Devin v3 requires an explicit organization ID")
        self.token, self.version, self.org_id = token, api_version, org_id
        self.max_acu_limit = max_acu_limit
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)

    def _url(self) -> str:
        if self.version == "v1":
            return "https://api.devin.ai/v1/sessions"
        return "https://api.devin.ai/v3/organizations/" + quote(self.org_id, safe="") + "/sessions"

    def _call(self, method: str, url: str, body=None) -> SessionResponse:
        try:
            response = self.client.request(
                method,
                url,
                json=body,
                headers={"Authorization": "Bearer " + self.token.get_secret_value()},
            )
            if response.status_code not in {200, 201}:
                raise ValueError(f"Devin API returned HTTP {response.status_code}; body withheld")
            return SessionResponse.model_validate(response.json())
        except ValueError as error:
            if str(error).startswith("Devin API returned HTTP"):
                raise
            raise ValueError("Invalid Devin API response; body withheld") from None
        except httpx.HTTPError:
            # A create may have succeeded remotely: never retry it automatically.
            raise ValueError(
                "Devin request failed; inspect the dashboard before retrying creation"
            ) from None

    def run(self, task: FixTask, repo: Path, *, approved: bool = False) -> FixResult:
        if not approved:
            raise ValueError("Mohith must explicitly approve a real Devin session before creation")
        if self.version == "v1":
            body = CreateV1(prompt=task_markdown(task), max_acu_limit=self.max_acu_limit)
        else:
            body = CreateV3(
                prompt=task_markdown(task), max_acu_limit=self.max_acu_limit, repos=[task.repo_url]
            )
        session = self._call("POST", self._url(), body.model_dump(mode="json"))
        return self._result(task.id, session)

    def poll(self, task_id: str, session_id: str) -> FixResult:
        session = self._call("GET", self._url() + "/" + quote(session_id, safe=""))
        if session.session_id != session_id:
            raise ValueError("Devin returned a different session identity")
        return self._result(task_id, session)

    def _result(self, task_id: str, session: SessionResponse) -> FixResult:
        urls = [p.pr_url or p.url for p in session.pull_requests]
        if session.pull_request:
            urls.append(session.pull_request.pr_url or session.pull_request.url)
        pr_url = next(
            (
                url
                for url in urls
                if url
                and urlsplit(url).scheme == "https"
                and urlsplit(url).netloc == "github.com"
                and urlsplit(url).path.startswith("/mohi-devhub/cachekit/pull/")
            ),
            None,
        )
        state = session.status_enum or session.status
        status = (
            "failed"
            if state in {"error", "failed"}
            else ("finished" if state in {"exit", "finished", "stopped"} else "running")
        )
        session_url = (
            session.url
            if session.url
            and urlsplit(session.url).scheme == "https"
            and (urlsplit(session.url).netloc in {"app.devin.ai", "devin.ai"})
            else None
        )
        return FixResult(
            task_id=task_id,
            status=status,
            pr_url=pr_url,
            session_id=session.session_id,
            session_url=session_url,
            log=["Only the redacted fix task was submitted; no private logs attached."],
        )
