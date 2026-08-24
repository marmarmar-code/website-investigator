from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .models import ChangeEvent, Evidence, Finding, Observation

HIGH_CATEGORIES = {"paywall", "publishing_platform"}
MEDIUM_CATEGORIES = {"consent", "analytics", "advertising"}


def _event_id(target_id: str | None, event_type: str, old: Any, new: Any) -> str:
    payload = json.dumps(
        {"target": target_id, "type": event_type, "old": old, "new": new},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _event(
    observation: Observation,
    *,
    event_type: str,
    category: str,
    severity: str,
    summary: str,
    old: Any = None,
    new: Any = None,
    evidence: list[Evidence] | None = None,
    methodology_change: bool = False,
) -> ChangeEvent:
    return ChangeEvent(
        id=_event_id(observation.target_id, event_type, old, new),
        target_id=observation.target_id,
        event_type=event_type,
        category=category,
        severity=severity,
        summary=summary,
        old_value=old,
        new_value=new,
        evidence=evidence or [],
        observed_at=observation.completed_at or datetime.now(UTC),
        methodology_change=methodology_change,
    )


def _finding_map(observation: Observation) -> dict[str, Finding]:
    return {finding.id: finding for finding in observation.findings}


def _severity_for_category(category: str) -> str:
    if category in HIGH_CATEGORIES:
        return "high"
    if category in MEDIUM_CATEGORIES:
        return "medium"
    return "low"


def compare_observations(old: Observation, new: Observation) -> list[ChangeEvent]:
    if old.target_id and new.target_id and old.target_id != new.target_id:
        raise ValueError("Cannot compare observations from different target IDs")

    if old.methodology_version != new.methodology_version:
        return [
            _event(
                new,
                event_type="methodology.changed",
                category="methodology",
                severity="info",
                summary=(
                    "Detection methodology changed; the new observation must be treated as a "
                    "re-baseline, not as proof that the website changed."
                ),
                old=old.methodology_version,
                new=new.methodology_version,
                methodology_change=True,
            )
        ]

    events: list[ChangeEvent] = []
    old_findings = _finding_map(old)
    new_findings = _finding_map(new)

    for finding_id in sorted(new_findings.keys() - old_findings.keys()):
        finding = new_findings[finding_id]
        events.append(
            _event(
                new,
                event_type="technology.added",
                category=finding.category,
                severity=_severity_for_category(finding.category),
                summary=f"First observed signal for {finding.name}.",
                new={
                    "id": finding.id,
                    "name": finding.name,
                    "confidence": finding.confidence,
                    "identifiers": finding.identifiers,
                },
                evidence=finding.evidence,
            )
        )

    for finding_id in sorted(old_findings.keys() - new_findings.keys()):
        finding = old_findings[finding_id]
        events.append(
            _event(
                new,
                event_type="technology.removed_candidate",
                category=finding.category,
                severity=_severity_for_category(finding.category),
                summary=f"Signal for {finding.name} was not observed in this scan.",
                old={
                    "id": finding.id,
                    "name": finding.name,
                    "confidence": finding.confidence,
                    "identifiers": finding.identifiers,
                },
                evidence=finding.evidence,
            )
        )

    for finding_id in sorted(old_findings.keys() & new_findings.keys()):
        previous = old_findings[finding_id]
        current = new_findings[finding_id]
        old_value = {
            "confidence": previous.confidence,
            "identifiers": sorted(previous.identifiers),
        }
        new_value = {
            "confidence": current.confidence,
            "identifiers": sorted(current.identifiers),
        }
        if old_value != new_value:
            events.append(
                _event(
                    new,
                    event_type="technology.signal_changed",
                    category=current.category,
                    severity="medium" if current.category in HIGH_CATEGORIES else "low",
                    summary=f"The observed signal for {current.name} changed.",
                    old=old_value,
                    new=new_value,
                    evidence=current.evidence,
                )
            )

    old_robots = {
        item.user_agent: {
            "allowed": item.allowed_at_root,
            "explicit": item.explicit_group,
            "directives": item.directives,
        }
        for item in old.robots_policies
    }
    new_robots = {
        item.user_agent: {
            "allowed": item.allowed_at_root,
            "explicit": item.explicit_group,
            "directives": item.directives,
        }
        for item in new.robots_policies
    }
    for crawler in sorted(set(old_robots) | set(new_robots)):
        before = old_robots.get(crawler)
        after = new_robots.get(crawler)
        if before != after:
            events.append(
                _event(
                    new,
                    event_type="robots.policy_changed",
                    category="crawler_policy",
                    severity="high" if crawler != "*" else "medium",
                    summary=f"robots.txt policy first observed as changed for {crawler}.",
                    old=before,
                    new=after,
                    evidence=[
                        Evidence(
                            kind="robots",
                            source="robots.txt",
                            value="; ".join((after or {}).get("directives", []))[:500],
                        )
                    ],
                )
            )

    for key in sorted(set(old.selected_headers) | set(new.selected_headers)):
        before = old.selected_headers.get(key)
        after = new.selected_headers.get(key)
        if before != after and key in {
            "server",
            "x-powered-by",
            "content-security-policy",
            "x-robots-tag",
        }:
            events.append(
                _event(
                    new,
                    event_type="http.header_changed",
                    category="infrastructure",
                    severity="low",
                    summary=f"HTTP header {key} changed.",
                    old=before,
                    new=after,
                    evidence=[Evidence(kind="header", source=key, value=after or "<absent>")],
                )
            )

    if old.metadata.generator != new.metadata.generator:
        events.append(
            _event(
                new,
                event_type="metadata.generator_changed",
                category="publishing_platform",
                severity="medium",
                summary="The public generator metadata changed.",
                old=old.metadata.generator,
                new=new.metadata.generator,
                evidence=[
                    Evidence(
                        kind="meta_generator",
                        source="meta:generator",
                        value=new.metadata.generator or "<absent>",
                    )
                ],
            )
        )

    old_domains = set(old.third_party_domains)
    new_domains = set(new.third_party_domains)
    added_domains = sorted(new_domains - old_domains)
    removed_domains = sorted(old_domains - new_domains)
    if added_domains:
        events.append(
            _event(
                new,
                event_type="third_party_domains.added",
                category="third_party",
                severity="low",
                summary=f"{len(added_domains)} third-party domain(s) were first observed.",
                new=added_domains,
                evidence=[
                    Evidence(kind="request_domain", source="browser", value=value)
                    for value in added_domains[:25]
                ],
            )
        )
    if removed_domains:
        events.append(
            _event(
                new,
                event_type="third_party_domains.removed_candidate",
                category="third_party",
                severity="low",
                summary=f"{len(removed_domains)} third-party domain(s) were not observed.",
                old=removed_domains,
            )
        )

    old_dns = {key: sorted(value) for key, value in old.dns.items()}
    new_dns = {key: sorted(value) for key, value in new.dns.items()}
    if old_dns != new_dns:
        events.append(
            _event(
                new,
                event_type="dns.changed",
                category="infrastructure",
                severity="low",
                summary="Public DNS observations changed.",
                old=old_dns,
                new=new_dns,
            )
        )

    tls_before = {
        "issuer": old.tls.issuer,
        "san": old.tls.san,
        "not_after": old.tls.not_after,
    }
    tls_after = {
        "issuer": new.tls.issuer,
        "san": new.tls.san,
        "not_after": new.tls.not_after,
    }
    if tls_before != tls_after:
        events.append(
            _event(
                new,
                event_type="tls.changed",
                category="infrastructure",
                severity="low",
                summary="TLS certificate metadata changed.",
                old=tls_before,
                new=tls_after,
            )
        )

    return sorted(events, key=lambda item: (item.severity, item.category, item.event_type, item.id))
