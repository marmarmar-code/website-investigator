from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import ChangeEvent, Observation

CATEGORY_INFO = (
    (
        "publishing_platform",
        "Publiseringsplattform",
        "Systemer som ser ut til å brukes for å lage og publisere innhold.",
    ),
    (
        "paywall",
        "Betaling og abonnement",
        "Teknologi knyttet til innlogging, abonnement, personalisering eller betalingsmur.",
    ),
    (
        "advertising",
        "Annonsering",
        "Teknologi som brukes til annonsevisning eller annonseauksjoner.",
    ),
    (
        "analytics",
        "Måling og analyse",
        "Verktøy som måler bruk, trafikk eller publikumsatferd.",
    ),
    (
        "consent",
        "Samtykke og personvern",
        "Løsninger som håndterer informasjonskapsler og samtykkevalg.",
    ),
    (
        "infrastructure",
        "Teknisk infrastruktur",
        "Tjenester som leverer, beskytter eller mellomlagrer nettstedet.",
    ),
)

STATUS_LABELS = {
    "success": "Fullført",
    "partial": "Fullført med forbehold",
    "failed": "Kunne ikke fullføres",
}
CONFIDENCE_LABELS = {
    "strong": "høy sikkerhet",
    "likely": "middels sikkerhet",
    "weak": "lav sikkerhet",
}


def _walk_structured_data(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_structured_data(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_structured_data(nested)


def _string_values(value: Any, *, limit: int = 20) -> list[str]:
    values = value if isinstance(value, list) else [value]
    output: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip() and item.strip() not in output:
            output.append(item.strip())
            if len(output) >= limit:
                break
    return output


def _organization_profiles(observation: Observation) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in _walk_structured_data(observation.metadata.structured_data):
        types = _string_values(item.get("@type") or item.get("type"))
        if not any("organization" in value.lower() for value in types):
            continue
        name_values = _string_values(item.get("legalName") or item.get("name"), limit=1)
        name = name_values[0] if name_values else ""
        url_values = _string_values(item.get("url"), limit=1)
        url = url_values[0] if url_values else ""
        if not name and not url:
            continue
        identity = (name.casefold(), url.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        profiles.append(
            {
                "name": name or "Navn ikke oppgitt",
                "url": url or None,
                "types": types,
                "same_as": _string_values(item.get("sameAs"), limit=10),
            }
        )
        if len(profiles) >= 10:
            break
    return profiles


def _finding_sections(observation: Observation) -> list[dict[str, Any]]:
    used_categories: set[str] = set()
    sections: list[dict[str, Any]] = []
    for key, label, description in CATEGORY_INFO:
        findings = sorted(
            (item for item in observation.findings if item.category == key),
            key=lambda item: (item.score, item.name.casefold()),
            reverse=True,
        )
        if findings:
            sections.append(
                {"key": key, "label": label, "description": description, "findings": findings}
            )
            used_categories.add(key)
    other = sorted(
        (item for item in observation.findings if item.category not in used_categories),
        key=lambda item: (item.score, item.name.casefold()),
        reverse=True,
    )
    if other:
        sections.append(
            {
                "key": "other",
                "label": "Andre teknologifunn",
                "description": "Andre offentlige teknologisignaler som ble observert.",
                "findings": other,
            }
        )
    return sections


def _health_checks(observation: Observation) -> list[dict[str, str]]:
    robots_values = [policy.allowed_at_root for policy in observation.robots_policies]
    if False in robots_values:
        robots_state = "Begrenset"
        robots_detail = "Minst én regel i robots.txt blokkerer innhenting fra forsiden."
    elif True in robots_values:
        robots_state = "Tillatt"
        robots_detail = "robots.txt tillater minst én registrert søkerobot på forsiden."
    else:
        robots_state = "Ikke avklart"
        robots_detail = "Ingen entydig regel for forsiden ble observert."
    return [
        {
            "label": "Kryptert forbindelse",
            "state": "Bekreftet" if observation.tls.available else "Ikke bekreftet",
            "detail": (
                "Nettstedet svarte med et gyldig HTTPS-sertifikat under undersøkelsen."
                if observation.tls.available
                else "Undersøkelsen kunne ikke bekrefte et gyldig HTTPS-sertifikat."
            ),
        },
        {
            "label": "Sikkerhetsregler i nettleseren",
            "state": (
                "Observert"
                if "content-security-policy" in observation.selected_headers
                else "Ikke observert"
            ),
            "detail": (
                "Nettstedet oppga en Content Security Policy på den undersøkte siden."
                if "content-security-policy" in observation.selected_headers
                else "Ingen Content Security Policy ble observert på den undersøkte siden."
            ),
        },
        {"label": "Søkerobot-regler", "state": robots_state, "detail": robots_detail},
    ]


def _report_context(observation: Observation) -> dict[str, Any]:
    seller_counts: dict[str, dict[str, int | str]] = {}
    for entry in observation.ads_txt.entries:
        row = seller_counts.setdefault(
            entry.seller_domain,
            {"domain": entry.seller_domain, "direct": 0, "reseller": 0},
        )
        relationship = entry.relationship.lower()
        row[relationship] = int(row[relationship]) + 1
    direct_ads = sum(item.relationship == "DIRECT" for item in observation.ads_txt.entries)
    reseller_ads = sum(item.relationship == "RESELLER" for item in observation.ads_txt.entries)
    completed = observation.completed_at.astimezone(UTC) if observation.completed_at else None
    important = sorted(
        observation.findings,
        key=lambda item: (item.score, item.name.casefold()),
        reverse=True,
    )[:6]
    return {
        "status_label": STATUS_LABELS[observation.status],
        "scan_label": "Grundig undersøkelse" if observation.scan_mode == "deep" else "Hurtigsjekk",
        "completed_label": completed.strftime("%d.%m.%Y kl. %H:%M UTC") if completed else "—",
        "confidence_labels": CONFIDENCE_LABELS,
        "important_findings": important,
        "finding_sections": _finding_sections(observation),
        "organizations": _organization_profiles(observation),
        "health_checks": _health_checks(observation),
        "ads_summary": {
            "available": observation.ads_txt.available,
            "entries": len(observation.ads_txt.entries),
            "sellers": len({item.seller_domain for item in observation.ads_txt.entries}),
            "direct": direct_ads,
            "reseller": reseller_ads,
            "invalid": observation.ads_txt.invalid_lines,
            "truncated": observation.ads_txt.truncated,
            "sellers_ranked": sorted(
                seller_counts.values(),
                key=lambda item: (
                    int(item["direct"]) + int(item["reseller"]),
                    str(item["domain"]),
                ),
                reverse=True,
            )[:25],
        },
    }


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
        **_report_context(observation),
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
