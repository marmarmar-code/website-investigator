from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from website_investigator.models import Observation
from website_investigator.on_demand import (
    private_repository_is_clean,
    run_on_demand_investigation,
    sync_private_paths,
)


def _observation(*, status: str = "success") -> Observation:
    item = Observation(
        schema_version=1,
        methodology_version="test-method",
        engine_version="0.3.0",
        requested_url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        registrable_domain="example.com",
        status=status,
        completed_at=datetime.now(UTC),
    )
    if status == "failed":
        item.errors = ["controlled test failure"]
    return item


def test_on_demand_report_stays_in_private_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "website_investigator.on_demand.scan_website",
        lambda *args, **kwargs: _observation(),
    )

    result = run_on_demand_investigation(
        tmp_path,
        "example.com",
        source="slack",
        requested_by="U123TEST",
        request_context={"team_id": "T123TEST", "channel_id": "C123TEST"},
        request_id="request-1",
    )

    assert "example" not in result.target_id
    assert result.report_path == tmp_path / "reports" / "requests" / "request-1.html"
    assert result.report_path.exists()
    request_path = tmp_path / "data" / "requests" / datetime.now(UTC).date().isoformat()
    payload = json.loads((request_path / "request-1.json").read_text(encoding="utf-8"))
    assert payload["source"] == "slack"
    assert payload["requested_by"] == "U123TEST"
    assert payload["request_context"] == {
        "team_id": "T123TEST",
        "channel_id": "C123TEST",
    }
    assert payload["observation"]["requested_url"] == "https://example.com"
    assert (tmp_path / "data" / "current" / f"{result.target_id}.json").exists()
    assert (tmp_path / "reports" / "latest" / f"{result.target_id}.html").exists()


def test_failed_on_demand_scan_preserves_last_valid_result(tmp_path, monkeypatch):
    scans = iter((_observation(), _observation(status="failed")))
    monkeypatch.setattr(
        "website_investigator.on_demand.scan_website",
        lambda *args, **kwargs: next(scans),
    )

    first = run_on_demand_investigation(
        tmp_path,
        "example.com",
        source="slack",
        requested_by="U123TEST",
        request_id="request-1",
    )
    current = tmp_path / "data" / "current" / f"{first.target_id}.json"
    before = current.read_bytes()
    failed = run_on_demand_investigation(
        tmp_path,
        "example.com",
        source="slack",
        requested_by="U123TEST",
        request_id="request-2",
    )

    assert failed.observation.status == "failed"
    assert failed.report_path.exists()
    assert current.read_bytes() == before


def test_on_demand_request_id_cannot_escape_runtime(tmp_path):
    with pytest.raises(ValueError, match="Invalid request ID"):
        run_on_demand_investigation(
            tmp_path,
            "example.com",
            source="slack",
            requested_by="U123TEST",
            request_id="../../outside",
        )


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_private_sync_commits_only_generated_paths(tmp_path):
    runtime = tmp_path / "runtime"
    remote = tmp_path / "remote.git"
    runtime.mkdir()
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(runtime, "init", "-b", "main")
    _git(runtime, "config", "user.name", "Website Investigator test")
    _git(runtime, "config", "user.email", "test@example.invalid")
    _git(runtime, "remote", "add", "origin", str(remote))
    (runtime / "README.md").write_text("private\n", encoding="utf-8")
    _git(runtime, "add", "README.md")
    _git(runtime, "commit", "-m", "Initial private runtime")
    _git(runtime, "push", "-u", "origin", "main")
    assert private_repository_is_clean(runtime)

    generated = runtime / "reports" / "requests" / "request-1.html"
    generated.parent.mkdir(parents=True)
    generated.write_text("private test report", encoding="utf-8")
    synced = sync_private_paths(
        runtime,
        (generated,),
        commit_message="Record Slack investigation request-1",
        clean_before_write=True,
    )

    assert synced.status == "synced"
    assert private_repository_is_clean(runtime)
    assert _git(runtime, "show", "--format=%s", "--no-patch", "HEAD").stdout.strip() == (
        "Record Slack investigation request-1"
    )
    assert _git(runtime, "diff", "HEAD^", "--name-only").stdout.strip() == (
        "reports/requests/request-1.html"
    )
