"""Local ingest and deterministic analysis commands."""

import json
from enum import StrEnum
from typing import Annotated

import typer

from cachekit import __version__
from cachekit.models import Report, RequestRecord

app = typer.Typer(no_args_is_help=True, help="Inspect and improve prompt-cache reuse.")


def show_version(value: bool) -> None:
    if value:
        typer.echo(f"cachekit {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool, typer.Option("--version", callback=show_version, is_eager=True)
    ] = False,
) -> None:
    """Deterministic prompt-cache analysis."""


class SchemaName(StrEnum):
    request = "RequestRecord"
    report = "Report"


@app.command()
def schema(model: Annotated[SchemaName, typer.Option()] = SchemaName.request) -> None:
    """Print the JSON schema for a shared file/API contract."""
    cls = RequestRecord if model == SchemaName.request else Report
    typer.echo(json.dumps(cls.model_json_schema(), sort_keys=True, indent=2))



def main() -> None:
    app()


if __name__ == "__main__":
    main()
