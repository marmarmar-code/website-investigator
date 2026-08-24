from __future__ import annotations

import hashlib
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import Observation
from .reports import write_observation_report
from .safety import UnsafeTargetError, normalize_url
from .scanner import scan_website
from .util import write_json


@dataclass(slots=True)
class InvestigationResult:
    request_id: str
    target_id: str
    observation: Observation
    report_path: Path
    saved_paths: tuple[Path, ...]


@dataclass(slots=True)
class PrivateSyncResult:
    status: str
    detail: str


def _request_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:10]}"


def _opaque_target_id(url: str) -> str:
    try:
        value = normalize_url(url)
    except (UnsafeTargetError, ValueError):
        value = url.strip()
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"site-{digest}"


def run_on_demand_investigation(
    runtime: Path,
    url: str,
    *,
    source: str,
    requested_by: str,
    request_context: dict[str, str] | None = None,
    deep: bool = True,
    request_id: str | None = None,
) -> InvestigationResult:
    runtime = runtime.resolve()
    request_id = request_id or _request_id()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", request_id):
        raise ValueError("Invalid request ID")
    target_id = _opaque_target_id(url)
    observation = scan_website(url, target_id=target_id, deep=deep)
    completed = observation.completed_at or datetime.now(UTC)

    request_path = (
        runtime
        / "data"
        / "requests"
        / completed.astimezone(UTC).date().isoformat()
        / f"{request_id}.json"
    )
    request_payload = {
        "schema_version": 1,
        "request_id": request_id,
        "source": source,
        "requested_by": requested_by,
        "request_context": request_context or {},
        "requested_at": observation.started_at.isoformat(),
        "completed_at": completed.isoformat(),
        "observation": observation.model_dump(mode="json"),
    }
    write_json(request_path, request_payload)

    report_path = runtime / "reports" / "requests" / f"{request_id}.html"
    write_observation_report(
        report_path,
        observation,
        display_name=observation.host or "Website investigation",
    )
    saved_paths: list[Path] = [request_path, report_path]

    if observation.status != "failed":
        current_path = runtime / "data" / "current" / f"{target_id}.json"
        latest_report = runtime / "reports" / "latest" / f"{target_id}.html"
        write_json(current_path, observation)
        write_observation_report(
            latest_report,
            observation,
            display_name=observation.host or "Website investigation",
        )
        saved_paths.extend((current_path, latest_report))

    return InvestigationResult(
        request_id=request_id,
        target_id=target_id,
        observation=observation,
        report_path=report_path,
        saved_paths=tuple(saved_paths),
    )


def private_repository_is_clean(runtime: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return completed.returncode == 0 and not completed.stdout.strip()


def sync_private_paths(
    runtime: Path,
    paths: tuple[Path, ...],
    *,
    commit_message: str,
    clean_before_write: bool,
) -> PrivateSyncResult:
    runtime = runtime.resolve()
    if not clean_before_write:
        return PrivateSyncResult(
            status="local_only",
            detail="The private repository already had local changes.",
        )

    relative_paths: list[str] = []
    for path in paths:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(runtime)
        except ValueError:
            return PrivateSyncResult(
                status="error",
                detail="A generated path was outside the private runtime.",
            )
        if resolved.exists():
            relative_paths.append(relative.as_posix())
    if not relative_paths:
        return PrivateSyncResult(status="unchanged", detail="No generated files changed.")

    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if root.returncode != 0 or Path(root.stdout.strip()).resolve() != runtime:
        return PrivateSyncResult(
            status="error",
            detail="The runtime is not the root of its private Git repository.",
        )

    staged = subprocess.run(
        ["git", "add", "--", *relative_paths],
        cwd=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if staged.returncode != 0:
        return PrivateSyncResult(status="error", detail="Could not stage the private report.")

    changed = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *relative_paths],
        cwd=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if changed.returncode == 0:
        return PrivateSyncResult(status="unchanged", detail="No generated files changed.")
    if changed.returncode != 1:
        return PrivateSyncResult(status="error", detail="Could not inspect the private changes.")

    committed = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", commit_message],
        cwd=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if committed.returncode != 0:
        subprocess.run(
            ["git", "restore", "--staged", "--", *relative_paths],
            cwd=runtime,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return PrivateSyncResult(status="error", detail="Could not commit the private report.")

    pushed = subprocess.run(
        ["git", "push", "origin", "HEAD:main"],
        cwd=runtime,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if pushed.returncode != 0:
        return PrivateSyncResult(
            status="local_only",
            detail="The report is committed locally, but the private push failed.",
        )
    return PrivateSyncResult(status="synced", detail="Saved to the private repository.")
