from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from website_investigator.models import Evidence, Finding, Observation, TargetConfig
from website_investigator.runtime import run_monitor


def observation(with_paywall: bool = False, *, status: str = "success") -> Observation:
    item = Observation(
        schema_version=1,
        methodology_version="2026-08-21.1",
        engine_version="0.1.0",
        target_id="target-1",
        requested_url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        registrable_domain="example.com",
        status=status,
        completed_at=datetime.now(UTC),
    )
    if with_paywall:
        item.findings = [
            Finding(
                id="paywall.piano",
                name="Piano",
                category="paywall",
                confidence="strong",
                score=90,
                evidence=[Evidence(kind="script_url", source="script", value="tinypass.com")],
            )
        ]
    return item


def setup_runtime(path: Path) -> None:
    (path / "config").mkdir(parents=True)
    (path / "config" / "targets.yml").write_text(
        yaml.safe_dump(
            {
                "targets": [
                    {
                        "id": "target-1",
                        "name": "Private target",
                        "url": "https://example.com",
                    }
                ]
            }
        )
    )
    (path / "engine.lock").write_text("engine:\n  version: 0.1.0\n")


def test_runtime_baselines_then_creates_event(tmp_path, monkeypatch):
    setup_runtime(tmp_path)
    scans = iter([observation(False), observation(True)])
    monkeypatch.setattr("website_investigator.runtime.scan_website", lambda *a, **k: next(scans))

    first = run_monitor(tmp_path, notify=False)
    assert first.baselined == 1
    assert first.events_created == 0

    second = run_monitor(tmp_path, notify=False)
    assert second.events_created == 1
    assert list((tmp_path / "notifications" / "pending").glob("*.json"))


def test_identical_monitor_run_does_not_rewrite_runtime(tmp_path, monkeypatch):
    setup_runtime(tmp_path)
    scans = iter([observation(False), observation(False)])
    monkeypatch.setattr("website_investigator.runtime.scan_website", lambda *a, **k: next(scans))

    first = run_monitor(tmp_path, notify=False)
    assert first.baselined == 1
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    second = run_monitor(tmp_path, notify=False)
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert second.events_created == 0
    assert before == after


def test_failed_scan_preserves_last_valid_observation(tmp_path, monkeypatch):
    setup_runtime(tmp_path)
    failed = observation(False, status="failed")
    failed.errors = ["controlled test failure"]
    scans = iter([observation(False), failed])
    monkeypatch.setattr("website_investigator.runtime.scan_website", lambda *a, **k: next(scans))

    run_monitor(tmp_path, notify=False)
    current = tmp_path / "data" / "current" / "target-1.json"
    before = current.read_bytes()
    result = run_monitor(tmp_path, notify=False)

    assert result.failed == 1
    assert current.read_bytes() == before


def test_removal_requires_two_consecutive_comparable_scans(tmp_path, monkeypatch):
    setup_runtime(tmp_path)
    scans = iter([observation(True), observation(False), observation(False)])
    monkeypatch.setattr("website_investigator.runtime.scan_website", lambda *a, **k: next(scans))

    run_monitor(tmp_path, notify=False)
    first_absence = run_monitor(tmp_path, notify=False)
    second_absence = run_monitor(tmp_path, notify=False)

    assert first_absence.events_created == 0
    assert second_absence.events_created == 1
    event_files = list((tmp_path / "data" / "events").rglob("*.json"))
    event_payload = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert event_payload["event_type"] == "technology.removed"


def test_target_id_cannot_escape_runtime_paths():
    with pytest.raises(ValueError):
        TargetConfig(id="../../outside", name="Unsafe", url="https://example.com")
