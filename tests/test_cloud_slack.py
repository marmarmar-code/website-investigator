from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from website_investigator.cloud_slack import AAD, decrypt_slack_job, run_cloud_slack_job

TEST_KEY_BYTES = bytes(range(32))
TEST_KEY = base64.urlsafe_b64encode(TEST_KEY_BYTES).decode().rstrip("=")


def _encode(payload: dict[str, object]) -> str:
    nonce = bytes(range(12))
    plaintext = json.dumps(payload, separators=(",", ":")).encode()
    ciphertext = AESGCM(TEST_KEY_BYTES).encrypt(nonce, plaintext, AAD)
    encoded_nonce = base64.urlsafe_b64encode(nonce).decode().rstrip("=")
    encoded_ciphertext = base64.urlsafe_b64encode(ciphertext).decode().rstrip("=")
    return f"v1.{encoded_nonce}.{encoded_ciphertext}"


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": 1,
        "request_id": "20260824T120000Z-a1b2c3d4e5",
        "url": "<https://example.com|example.com>",
        "user_id": "U123TEST",
        "team_id": "T123TEST",
        "channel_id": "C123TEST",
        "issued_at": 1_800_000_000,
    }
    payload.update(changes)
    return payload


def test_decrypts_fresh_authenticated_job():
    job = decrypt_slack_job(_encode(_payload()), TEST_KEY, now=1_800_000_030)

    assert job.url == "https://example.com"
    assert job.request_id == "20260824T120000Z-a1b2c3d4e5"
    assert job.user_id == "U123TEST"


def test_rejects_tampered_or_expired_job():
    token = _encode(_payload())
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(ValueError, match="Invalid"):
        decrypt_slack_job(token[:-1] + replacement, TEST_KEY, now=1_800_000_030)
    with pytest.raises(ValueError, match="Expired"):
        decrypt_slack_job(token, TEST_KEY, now=1_800_001_000)


def test_rejects_unexpected_payload_fields():
    with pytest.raises(ValueError, match="Invalid"):
        decrypt_slack_job(
            _encode(_payload(unexpected="value")),
            TEST_KEY,
            now=1_800_000_030,
        )


def test_cloud_job_checks_bot_workspace_before_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "website_investigator.cloud_slack.decrypt_slack_job",
        lambda token, key: SimpleNamespace(
            request_id="request-1",
            url="example.com",
            user_id="U123TEST",
            team_id="T123TEST",
            channel_id="C123TEST",
        ),
    )
    processed: list[object] = []
    monkeypatch.setattr(
        "website_investigator.cloud_slack.process_slack_job",
        lambda *args: processed.append(args),
    )

    class WrongWorkspaceClient:
        def auth_test(self):
            return {"team_id": "TOTHER1"}

    with pytest.raises(PermissionError, match="workspace"):
        run_cloud_slack_job(
            Path(tmp_path),
            job_token="encrypted-test-job",
            payload_key=TEST_KEY,
            bot_token="test-bot-token",
            client_factory=lambda token: WrongWorkspaceClient(),
        )
    assert not processed
