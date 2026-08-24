from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .diff import compare_observations
from .models import Observation
from .reports import write_observation_report
from .runtime import doctor as run_doctor
from .runtime import run_monitor
from .scanner import scan_website
from .util import read_json, write_json

app = typer.Typer(
    no_args_is_help=True,
    help="Evidence-first website inspection and private monitoring for journalists.",
)


@app.command()
def inspect(
    url: Annotated[str, typer.Argument(help="Public HTTP(S) URL or domain to inspect.")],
    deep: Annotated[
        bool,
        typer.Option("--deep", help="Use Playwright for dynamic browser signals."),
    ] = False,
    json_path: Annotated[
        Path | None,
        typer.Option("--json", help="Write normalized JSON observation."),
    ] = None,
    html_path: Annotated[
        Path | None,
        typer.Option("--html", help="Write a standalone HTML dossier."),
    ] = None,
    detector_pack: Annotated[
        Path | None,
        typer.Option("--detector-pack", help="Optional custom YAML detector pack."),
    ] = None,
) -> None:
    observation = scan_website(
        url,
        deep=deep,
        detector_pack_path=detector_pack,
    )
    if json_path:
        write_json(json_path, observation)
    if html_path:
        write_observation_report(html_path, observation)

    typer.echo(
        json.dumps(
            {
                "status": observation.status,
                "host": observation.host,
                "scan_mode": observation.scan_mode,
                "findings": len(observation.findings),
                "third_party_domains": len(observation.third_party_domains),
                "errors": observation.errors,
                "json": str(json_path) if json_path else None,
                "html": str(html_path) if html_path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if observation.status == "failed":
        raise typer.Exit(code=2)


@app.command()
def compare(
    old_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    new_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    old = Observation.model_validate(read_json(old_path))
    new = Observation.model_validate(read_json(new_path))
    events = compare_observations(old, new)
    payload = [event.model_dump(mode="json") for event in events]
    if output:
        write_json(output, payload)
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def monitor(
    runtime: Annotated[Path, typer.Option("--runtime", exists=True, file_okay=False)],
    no_notify: Annotated[bool, typer.Option("--no-notify")] = False,
) -> None:
    result = run_monitor(runtime, notify=not no_notify)
    payload = {
        "scanned": result.scanned,
        "baselined": result.baselined,
        "failed": result.failed,
        "events_created": result.events_created,
        "notifications_delivered": result.notifications_delivered,
        "notifications_pending": result.notifications_pending,
    }
    typer.echo(json.dumps(payload, indent=2))
    if result.failed and result.failed == result.scanned:
        raise typer.Exit(code=2)


@app.command()
def doctor(
    runtime: Annotated[Path, typer.Option("--runtime", exists=True, file_okay=False)],
) -> None:
    checks = run_doctor(runtime)
    required_failures = 0
    for name, passed, detail in checks:
        optional = name == "notifications_configured"
        marker = "OK" if passed else ("OPTIONAL" if optional else "FAIL")
        typer.echo(f"[{marker}] {name}: {detail}")
        if not passed and not optional:
            required_failures += 1
    if required_failures:
        raise typer.Exit(code=1)


@app.command()
def serve(
    runtime: Annotated[Path, typer.Option("--runtime", exists=True, file_okay=False)],
    host: Annotated[str, typer.Option(help="Bind locally by default.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8765,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter("Install website-investigator[web]") from exc
    from .web import create_app

    if host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get(
        "WI_ALLOW_REMOTE_UI"
    ):
        raise typer.BadParameter(
            "Remote binding is disabled by default. Set WI_ALLOW_REMOTE_UI=1 deliberately."
        )
    uvicorn.run(create_app(runtime), host=host, port=port, access_log=False)


@app.command()
def version() -> None:
    typer.echo(__version__)


if __name__ == "__main__":
    app()
