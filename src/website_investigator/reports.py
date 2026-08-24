from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import ChangeEvent, Observation


def _environment() -> Environment:
    template_dir = resources.files("website_investigator").joinpath("templates")
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_observation(
    observation: Observation,
    *,
    events: list[ChangeEvent] | None = None,
    display_name: str | None = None,
) -> str:
    template = _environment().get_template("observation.html")
    return template.render(
        observation=observation,
        events=events or [],
        display_name=display_name,
        raw_json=json.dumps(observation.model_dump(mode="json"), ensure_ascii=False, indent=2),
    )


def write_observation_report(
    path: Path,
    observation: Observation,
    *,
    events: list[ChangeEvent] | None = None,
    display_name: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_observation(observation, events=events, display_name=display_name),
        encoding="utf-8",
    )


def render_index(items: list[dict[str, Any]]) -> str:
    template = _environment().get_template("index.html")
    return template.render(items=items)
