from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .diff import compare_observations
from .models import ChangeEvent, Observation, RuntimeConfig, TargetConfig
from .reports import write_observation_report
from .safety import UnsafeTargetError, validate_public_url
from .scanner import scan_website
from .util import read_json, write_json


@dataclass(slots=True)
class MonitorResult:
    scanned: int = 0
    baselined: int = 0
    failed: int = 0
    events_created: int = 0
    notifications_delivered: int = 0
    notifications_pending: int = 0


def load_runtime_config(runtime: Path) -> RuntimeConfig:
    config_path = runtime / "config" / "targets.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing runtime config: {config_path}")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return RuntimeConfig.model_validate(payload)


def ensure_runtime_layout(runtime: Path) -> None:
    for relative in (
        "data/current",
        "data/events",
        "data/status",
        "notifications/pending",
        "notifications/delivered",
        "reports/latest",
    ):
        (runtime / relative).mkdir(parents=True, exist_ok=True)


def _candidate_key(event: ChangeEvent) -> str:
    payload = json.dumps(
        {
            "target": event.target_id,
            "type": event.event_type,
            "old": event.old_value,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _confirmed_events(
    runtime: Path,
    target_id: str,
    events: list[ChangeEvent],
    observation: Observation,
) -> tuple[list[ChangeEvent], bool]:
    path = runtime / "data" / "status" / "removal_candidates.json"
    candidates: dict[str, dict[str, Any]] = read_json(path) if path.exists() else {}
    before = json.dumps(candidates, ensure_ascii=False, sort_keys=True)
    seen_keys: set[str] = set()
    output: list[ChangeEvent] = []

    if any(event.methodology_change for event in events):
        candidates = {
            key: state
            for key, state in candidates.items()
            if state.get("target_id") != target_id
        }

    for event in events:
        if not event.event_type.endswith("_candidate"):
            output.append(event)
            continue
        key = _candidate_key(event)
        seen_keys.add(key)
        state = candidates.get(key, {"count": 0})
        state["count"] = int(state.get("count", 0)) + 1
        state["target_id"] = target_id
        state["last_observed"] = event.observed_at.isoformat()
        state["event"] = event.model_dump(mode="json")
        candidates[key] = state
        if state["count"] >= 2:
            event.event_type = event.event_type.removesuffix("_candidate")
            event.summary = event.summary.rstrip(".") + " in two consecutive comparable scans."
            output.append(event)
            candidates.pop(key, None)

    current_finding_ids = {finding.id for finding in observation.findings}
    current_domains = set(observation.third_party_domains)
    for key, state in list(candidates.items()):
        if state.get("target_id") != target_id or key in seen_keys:
            continue
        try:
            pending = ChangeEvent.model_validate(state["event"])
        except (KeyError, TypeError, ValueError):
            candidates.pop(key, None)
            continue
        still_missing = False
        if pending.event_type == "technology.removed_candidate":
            finding_id = (pending.old_value or {}).get("id")
            still_missing = bool(finding_id and finding_id not in current_finding_ids)
        elif pending.event_type == "third_party_domains.removed_candidate":
            missing = sorted(set(pending.old_value or []) - current_domains)
            if missing:
                pending.old_value = missing
                still_missing = True
        if not still_missing:
            candidates.pop(key, None)
            continue
        state["count"] = int(state.get("count", 0)) + 1
        pending.observed_at = observation.completed_at or datetime.now(UTC)
        state["last_observed"] = pending.observed_at.isoformat()
        state["event"] = pending.model_dump(mode="json")
        if state["count"] >= 2:
            pending.event_type = pending.event_type.removesuffix("_candidate")
            pending.summary = (
                pending.summary.rstrip(".") + " in two consecutive comparable scans."
            )
            output.append(pending)
            candidates.pop(key, None)

    after = json.dumps(candidates, ensure_ascii=False, sort_keys=True)
    changed = before != after
    if candidates or path.exists():
        write_json(path, candidates)
    return output, changed


def _write_event(runtime: Path, event: ChangeEvent, target: TargetConfig) -> None:
    date = event.observed_at.astimezone(UTC).date().isoformat()
    event_path = runtime / "data" / "events" / date / f"{event.id}.json"
    payload = event.model_dump(mode="json")
    payload["target_name"] = target.name
    payload["target_url"] = target.url
    write_json(event_path, payload)

    notification_path = runtime / "notifications" / "pending" / f"{event.id}.json"
    write_json(
        notification_path,
        {
            "event_id": event.id,
            "target_id": target.id,
            "target_name": target.name,
            "title": f"Website Investigator: {event.severity.upper()} · {event.category}",
            "body": (
                f"{target.name}\n{event.summary}\n"
                f"First observed: {event.observed_at.isoformat()}"
            ),
            "created_at": datetime.now(UTC).isoformat(),
        },
    )


def _failure_state(
    runtime: Path,
    target: TargetConfig,
    observation: Observation,
) -> list[ChangeEvent]:
    path = runtime / "data" / "status" / f"{target.id}.json"
    state = read_json(path) if path.exists() else {}
    failures = int(state.get("consecutive_failures", 0)) + 1
    state.update(
        {
            "target_id": target.id,
            "consecutive_failures": failures,
            "last_failure": (observation.completed_at or datetime.now(UTC)).isoformat(),
            "last_error": observation.errors[-1] if observation.errors else "Unknown scan failure",
        }
    )
    write_json(path, state)
    if failures != 2:
        return []
    event = ChangeEvent(
        id=f"availability-{target.id}-{failures}",
        target_id=target.id,
        event_type="availability.repeated_failure",
        category="availability",
        severity="high",
        summary=(
            "The target failed two consecutive scans; "
            "the last valid observation was preserved."
        ),
        old_value=None,
        new_value={"consecutive_failures": failures, "error": state["last_error"]},
        observed_at=observation.completed_at or datetime.now(UTC),
    )
    return [event]


def _clear_failure_state(
    runtime: Path,
    target: TargetConfig,
    observation: Observation,
) -> bool:
    path = runtime / "data" / "status" / f"{target.id}.json"
    if not path.exists():
        return False
    state = read_json(path)
    if int(state.get("consecutive_failures", 0)) == 0:
        return False
    state.update(
        {
            "target_id": target.id,
            "consecutive_failures": 0,
            "last_success": (observation.completed_at or datetime.now(UTC)).isoformat(),
        }
    )
    return write_json(path, state)


def deliver_pending(runtime: Path) -> tuple[int, int]:
    pending_dir = runtime / "notifications" / "pending"
    delivered_dir = runtime / "notifications" / "delivered"
    urls = [
        item.strip()
        for item in os.environ.get("WI_APPRISE_URLS", "").splitlines()
        if item.strip()
    ]
    pending = sorted(pending_dir.glob("*.json"))
    if not pending or not urls:
        return 0, len(pending)

    try:
        import apprise
    except ImportError:
        return 0, len(pending)

    notifier = apprise.Apprise()
    for url in urls:
        notifier.add(url)
    delivered = 0
    for path in pending:
        payload = read_json(path)
        success = bool(notifier.notify(title=payload["title"], body=payload["body"]))
        if not success:
            continue
        delivered_dir.mkdir(parents=True, exist_ok=True)
        destination = delivered_dir / path.name
        shutil.move(str(path), str(destination))
        delivered += 1
    return delivered, len(list(pending_dir.glob("*.json")))


def run_monitor(runtime: Path, *, notify: bool = True) -> MonitorResult:
    runtime = runtime.resolve()
    ensure_runtime_layout(runtime)
    config = load_runtime_config(runtime)
    result = MonitorResult()

    for target in config.targets:
        if not target.enabled:
            continue
        result.scanned += 1
        observation = scan_website(
            target.url,
            target_id=target.id,
            deep=target.scan_mode == "deep",
        )
        current_path = runtime / "data" / "current" / f"{target.id}.json"

        if observation.status == "failed":
            result.failed += 1
            for event in _failure_state(runtime, target, observation):
                _write_event(runtime, event, target)
                result.events_created += 1
            continue

        failure_state_changed = _clear_failure_state(runtime, target, observation)
        if not current_path.exists():
            write_json(current_path, observation)
            write_observation_report(
                runtime / "reports" / "latest" / f"{target.id}.html",
                observation,
                display_name=target.name,
            )
            result.baselined += 1
            continue

        old = Observation.model_validate(read_json(current_path))
        events = compare_observations(old, observation)
        events, candidate_state_changed = _confirmed_events(
            runtime,
            target.id,
            events,
            observation,
        )
        for event in events:
            _write_event(runtime, event, target)
            result.events_created += 1

        if events or candidate_state_changed or failure_state_changed:
            # Persist only meaningful state transitions. An identical scan must not create a
            # timestamp-only commit in the private runtime repository.
            write_json(current_path, observation)
            write_observation_report(
                runtime / "reports" / "latest" / f"{target.id}.html",
                observation,
                events=events,
                display_name=target.name,
            )

    if notify:
        delivered, pending = deliver_pending(runtime)
        result.notifications_delivered = delivered
        result.notifications_pending = pending
    else:
        result.notifications_pending = len(
            list((runtime / "notifications" / "pending").glob("*.json"))
        )
    return result


def doctor(runtime: Path) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    runtime = runtime.resolve()
    checks.append(("runtime_exists", runtime.exists(), str(runtime)))
    config_path = runtime / "config" / "targets.yml"
    checks.append(("targets_config", config_path.exists(), str(config_path)))
    try:
        config = load_runtime_config(runtime)
        ids = [target.id for target in config.targets]
        checks.append(("unique_target_ids", len(ids) == len(set(ids)), f"{len(ids)} targets"))
        checks.append(("valid_targets", True, f"{len(config.targets)} target definitions parsed"))
        target_errors: list[str] = []
        for target in config.targets:
            if not target.enabled:
                continue
            try:
                validate_public_url(target.url)
            except (UnsafeTargetError, ValueError) as exc:
                target_errors.append(f"{target.id}: {exc}")
        checks.append(
            (
                "public_targets",
                not target_errors,
                "; ".join(target_errors) if target_errors else "enabled targets resolve publicly",
            )
        )
    except Exception as exc:
        checks.append(("valid_targets", False, str(exc)))
    lock_path = runtime / "engine.lock"
    if not lock_path.exists():
        checks.append(("engine_lock", False, str(lock_path)))
    else:
        try:
            lock_payload = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
            engine = lock_payload.get("engine", {})
            image = str(engine.get("image", ""))
            version = str(engine.get("version", ""))
            digest = str(engine.get("digest", ""))
            placeholder = digest == "sha256:REPLACE_WITH_PUBLISHED_IMAGE_DIGEST"
            digest_valid = bool(re.fullmatch(r"sha256:[0-9a-f]{64}", digest))
            lock_valid = (
                image.startswith("ghcr.io/")
                and version not in {"", "latest"}
                and ":latest" not in image
                and (placeholder or digest_valid)
                and engine.get("schema_version") == 1
            )
            detail = "release digest pending" if placeholder else f"{image}@{digest}"
            checks.append(("engine_lock", lock_valid, detail))
        except (AttributeError, TypeError, yaml.YAMLError) as exc:
            checks.append(("engine_lock", False, str(exc)))
    policies_path = runtime / "config" / "policies.yml"
    try:
        policies = yaml.safe_load(policies_path.read_text(encoding="utf-8"))
        checks.append(("policies_config", isinstance(policies, dict), str(policies_path)))
    except (OSError, yaml.YAMLError) as exc:
        checks.append(("policies_config", False, str(exc)))
    workflow_dir = runtime / ".github" / "workflows"
    workflow_files = (
        sorted(
            path.relative_to(runtime)
            for path in workflow_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
        )
        if workflow_dir.exists()
        else []
    )
    storage_only = not workflow_files
    workflow_detail = (
        "private runtime contains no workflows; execution belongs to the public repository"
        if storage_only
        else "private runtime workflow found: " + ", ".join(map(str, workflow_files))
    )
    checks.append(("runtime_actions_absent", storage_only, workflow_detail))
    checks.append(("schedule_disabled", storage_only, workflow_detail))
    checks.append(
        (
            "notifications_configured",
            bool(os.environ.get("WI_APPRISE_URLS", "").strip()),
            "optional; pending notifications are preserved when absent",
        )
    )
    return checks
