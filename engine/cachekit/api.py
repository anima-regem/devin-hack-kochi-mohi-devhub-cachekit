"""API foundation. Analysis endpoints are added with the report pipeline."""

from typing import Literal

from fastapi import FastAPI

from cachekit import __version__
from cachekit.models import BoundaryModel

app = FastAPI(title="cachekit", version=__version__)


class HealthResponse(BoundaryModel):
    status: Literal["ok"] = "ok"
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(version=__version__)
