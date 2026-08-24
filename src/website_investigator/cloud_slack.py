from __future__ import annotations

import base64
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import SlackRuntimeConfig
from .on_demand import InvestigationResult
from .slack_bridge import (
    SlackJob,
    is_authorized,
    parse_command_text,
    process_slack_job,
)

AAD = b"website-investigator-slack-v1"
IDENTIFIER_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{5,31}$")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _decode_base64url(value: str, *, expected_length: int | None = None) -> bytes:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid encrypted Slack payload")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid encrypted Slack payload") from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise ValueError("Invalid encrypted Slack payload")
    return decoded


def decrypt_slack_job(
    token: str,
    payload_key: str,
    *,
    now: int | None = None,
    max_age_seconds: int = 900,
) -> SlackJob:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError("Install website-investigator[cloud]") from exc

    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise ValueError("Invalid encrypted Slack payload")
    key = _decode_base64url(payload_key.strip(), expected_length=32)
    nonce = _decode_base64url(parts[1], expected_length=12)
    ciphertext = _decode_base64url(parts[2])
    if len(ciphertext) < 17:
        raise ValueError("Invalid encrypted Slack payload")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
        payload = json.loads(plaintext)
    except Exception as exc:
        raise ValueError("Invalid encrypted Slack payload") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "request_id",
        "url",
        "user_id",
        "team_id",
        "channel_id",
        "issued_at",
    }:
        raise ValueError("Invalid encrypted Slack payload")
    if payload["version"] != 1 or not isinstance(payload["issued_at"], int):
        raise ValueError("Invalid encrypted Slack payload")

    current = int(time.time()) if now is None else now
    if payload["issued_at"] > current + 60 or current - payload["issued_at"] > max_age_seconds:
        raise ValueError("Expired encrypted Slack payload")
    request_id = str(payload["request_id"])
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("Invalid encrypted Slack payload")

    identifiers = {
        "user_id": str(payload["user_id"]),
        "team_id": str(payload["team_id"]),
        "channel_id": str(payload["channel_id"]),
    }
    if any(not IDENTIFIER_PATTERN.fullmatch(value) for value in identifiers.values()):
        raise ValueError("Invalid encrypted Slack payload")

    return SlackJob(
        request_id=request_id,
        url=parse_command_text(str(payload["url"])),
        **identifiers,
    )


def _response_value(response: Any, key: str) -> str:
    try:
        value = response[key]
    except (KeyError, TypeError):
        value = getattr(response, key, None)
    return str(value) if value else ""


def run_cloud_slack_job(
    runtime: Path,
    *,
    job_token: str | None = None,
    payload_key: str | None = None,
    bot_token: str | None = None,
    client_factory: Callable[[str], Any] | None = None,
) -> InvestigationResult:
    job_token = job_token or os.environ.get("WI_SLACK_JOB", "")
    payload_key = payload_key or os.environ.get("WI_SLACK_PAYLOAD_KEY", "")
    bot_token = bot_token or os.environ.get("WI_SLACK_BOT_TOKEN", "")
    if not job_token or not payload_key or not bot_token:
        raise RuntimeError("Slack cloud credentials are incomplete")

    job = decrypt_slack_job(job_token, payload_key)
    if client_factory is None:
        try:
            from slack_sdk import WebClient
        except ImportError as exc:
            raise RuntimeError("Install website-investigator[slack]") from exc

        def build_client(token: str) -> Any:
            return WebClient(token=token)

        client_factory = build_client
    client = client_factory(bot_token)
    connected_team_id = _response_value(client.auth_test(), "team_id")
    config = SlackRuntimeConfig(
        enabled=True,
        workspace_id=job.team_id,
        scan_mode="deep",
        sync_private_repository=False,
    )
    if not is_authorized(
        config,
        team_id=job.team_id,
        user_id=job.user_id,
        channel_id=job.channel_id,
        connected_team_id=connected_team_id,
    ):
        raise PermissionError("Slack workspace mismatch")
    return process_slack_job(client, runtime, config, job)
