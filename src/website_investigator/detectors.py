from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .metadata import inline_script_sample
from .models import Evidence, Finding, MetadataObservation
from .util import host_from_url, truncate


@dataclass(slots=True)
class DetectionContext:
    html: bytes
    metadata: MetadataObservation
    headers: dict[str, str]
    cookie_names: list[str]
    request_domains: list[str]


def load_detector_pack(path: Path | None = None) -> dict[str, Any]:
    if path:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        packaged = resources.files("website_investigator.data").joinpath("detectors.yml")
        payload = yaml.safe_load(packaged.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("detectors"), list):
        raise ValueError("Detector pack must contain a detectors list")
    if not isinstance(payload.get("version"), str) or not payload["version"].strip():
        raise ValueError("Detector pack must declare a non-empty version")
    seen_ids: set[str] = set()
    allowed_sources = {
        "script_url",
        "html",
        "meta_generator",
        "header",
        "cookie_name",
        "request_domain",
    }
    for detector in payload["detectors"]:
        if not isinstance(detector, dict) or not detector.get("id"):
            raise ValueError("Every detector must be an object with an id")
        detector_id = str(detector["id"])
        if detector_id in seen_ids:
            raise ValueError(f"Duplicate detector id: {detector_id}")
        seen_ids.add(detector_id)
        if not detector.get("interpretation") or not detector.get("false_positive_note"):
            raise ValueError(
                f"Detector {detector_id} must document interpretation and false positives"
            )
        signals = detector.get("signals")
        if not isinstance(signals, list) or not signals:
            raise ValueError(f"Detector {detector_id} must define signals")
        for signal in signals:
            signal_type = str(signal.get("type", ""))
            if signal_type not in allowed_sources:
                raise ValueError(f"Detector {detector_id} has unknown signal type: {signal_type}")
            pattern = str(signal.get("pattern", ""))
            if not pattern:
                raise ValueError(f"Detector {detector_id} has an empty signal pattern")
            try:
                re.compile(pattern)
                if signal.get("capture"):
                    re.compile(str(signal["capture"]))
            except re.error as exc:
                raise ValueError(f"Detector {detector_id} has an invalid regex: {exc}") from exc
    return payload


def _sources(context: DetectionContext) -> dict[str, list[tuple[str, str]]]:
    html_text = context.html.decode("utf-8", errors="replace")[:1_500_000]
    inline = inline_script_sample(context.html)
    headers = [
        (name.lower(), f"{name.lower()}: {value}")
        for name, value in context.headers.items()
    ]
    return {
        "script_url": [(url, url) for url in context.metadata.scripts],
        "html": [("root_html", html_text + "\n" + inline)],
        "meta_generator": [("meta:generator", context.metadata.generator or "")],
        "header": headers,
        "cookie_name": [(name, name) for name in context.cookie_names],
        "request_domain": [(domain, domain) for domain in context.request_domains],
    }


def _confidence(score: int, thresholds: dict[str, int]) -> str | None:
    strong = int(thresholds.get("strong", 80))
    likely = int(thresholds.get("likely", 50))
    if score >= strong:
        return "strong"
    if score >= likely:
        return "likely"
    if score > 0:
        return "weak"
    return None


def run_detectors(
    context: DetectionContext,
    detector_pack: dict[str, Any],
    include_weak: bool = False,
) -> list[Finding]:
    sources = _sources(context)
    findings: list[Finding] = []

    for detector in detector_pack.get("detectors", []):
        score = 0
        evidence: list[Evidence] = []
        identifiers: set[str] = set()
        used_signal_indexes: set[int] = set()

        for index, signal in enumerate(detector.get("signals", [])):
            signal_type = str(signal.get("type", ""))
            pattern = str(signal.get("pattern", ""))
            if signal_type not in sources or not pattern:
                continue
            try:
                compiled = re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
            except re.error:
                continue

            for source_name, value in sources[signal_type]:
                match = compiled.search(value)
                if not match:
                    continue
                if index not in used_signal_indexes:
                    score += int(signal.get("weight", 0))
                    used_signal_indexes.add(index)
                matched_value = match.group(0)
                evidence.append(
                    Evidence(
                        kind=signal_type,
                        source=source_name,
                        value=truncate(matched_value, 300),
                        detail=truncate(value, 500) if signal_type != "html" else None,
                    )
                )
                capture = signal.get("capture")
                if capture:
                    try:
                        capture_match = re.search(str(capture), value, flags=re.IGNORECASE)
                        if capture_match:
                            identifiers.add(capture_match.group(1))
                    except (re.error, IndexError):
                        pass
                if len(evidence) >= 12:
                    break
            if len(evidence) >= 12:
                break

        confidence = _confidence(score, detector.get("thresholds", {}))
        if confidence is None or (confidence == "weak" and not include_weak):
            continue
        findings.append(
            Finding(
                id=str(detector["id"]),
                name=str(detector.get("name", detector["id"])),
                category=str(detector.get("category", "other")),
                confidence=confidence,
                score=min(score, 1000),
                evidence=evidence,
                interpretation=detector.get("interpretation"),
                false_positive_note=detector.get("false_positive_note"),
                identifiers=sorted(identifiers),
            )
        )

    return sorted(findings, key=lambda item: (item.category, item.name.lower()))


def request_domains_from_urls(urls: list[str]) -> list[str]:
    return sorted({host for url in urls if (host := host_from_url(url))})
