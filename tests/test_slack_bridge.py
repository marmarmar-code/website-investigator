from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from website_investigator.models import Evidence, Finding, Observation, SlackRuntimeConfig
from website_investigator.slack_bridge import (
    SlackJob,
    configure_slack,
    format_slack_summary,
    is_authorized,
    load_slack_config,
    parse_command_text,
    process_slack_job,
    render_launch_agent,
    store_slack_token,
)


class FakeSlackClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []

    def chat_postMessage(self, **kwargs: Any) -> dict[str, str]:
        self.messages.append(kwargs)
        return {"channel": "D_PRIVATE", "ts": "123.456"}

    def files_upload_v2(self, **kwargs: Any) -> dict[str, bool]:
        self.files.append(kwargs)
        return {"ok": True}


def _observation() -> Observation:
    return Observation(
        schema_version=1,
        methodology_version="test-method",
        engine_version="0.3.0",
        requested_url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        registrable_domain="example.com",
        scan_mode="deep",
        status="success",
        findings=[
            Finding(
                id="analytics.test",
                name="Test Analytics",
                category="analytics",
                confidence="strong",
                score=90,
                evidence=[Evidence(kind="script", source="test", value="test")],
            )
        ],
        third_party_domains=["third-party.invalid"],
        cookie_names=["test_cookie"],
        completed_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example.com", "example.com"),
        ("https://example.com", "https://example.com"),
        ("<https://example.com|example.com>", "https://example.com"),
    ],
)
def test_parse_slack_command(value, expected):
    assert parse_command_text(value) == expected


@pytest.mark.parametrize("value", ["", "help", "two domains.invalid"])
def test_parse_slack_command_rejects_ambiguous_input(value):
    with pytest.raises(ValueError):
        parse_command_text(value)


def test_slack_access_is_bound_to_connected_workspace():
    config = SlackRuntimeConfig(enabled=True, workspace_id="T_ALLOWED")
    assert is_authorized(
        config,
        team_id="T_ALLOWED",
        user_id="U1",
        channel_id="C1",
        connected_team_id="T_ALLOWED",
    )
    assert not is_authorized(
        config,
        team_id="T_OTHER",
        user_id="U1",
        channel_id="C1",
        connected_team_id="T_ALLOWED",
    )


def test_slack_access_can_be_limited_to_users_and_channels():
    config = SlackRuntimeConfig(
        enabled=True,
        workspace_id="T1",
        allowed_user_ids=["U_ALLOWED"],
        allowed_channel_ids=["C_ALLOWED"],
    )
    assert is_authorized(
        config,
        team_id="T1",
        user_id="U_ALLOWED",
        channel_id="C_ALLOWED",
        connected_team_id="T1",
    )
    assert not is_authorized(
        config,
        team_id="T1",
        user_id="U_OTHER",
        channel_id="C_ALLOWED",
        connected_team_id="T1",
    )


def test_slack_result_is_sent_only_to_requester_dm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "website_investigator.on_demand.scan_website",
        lambda *args, **kwargs: _observation(),
    )
    monkeypatch.setattr(
        "website_investigator.slack_bridge.private_repository_is_clean",
        lambda runtime: pytest.fail(
            "Git must not be required when the outer workflow persists private outputs"
        ),
    )
    client = FakeSlackClient()
    job = SlackJob(
        request_id="request-1",
        url="example.com",
        user_id="U_REQUESTER",
        team_id="T1",
        channel_id="C_ORIGINAL",
    )

    result = process_slack_job(
        client,
        tmp_path,
        SlackRuntimeConfig(enabled=True, workspace_id="T1", sync_private_repository=False),
        job,
    )

    assert result.observation.status == "success"
    assert client.messages[0]["channel"] == "U_REQUESTER"
    assert all(message["channel"] != "C_ORIGINAL" for message in client.messages)
    assert client.files[0]["channel"] == "D_PRIVATE"
    assert client.files[0]["file"].startswith(str(tmp_path))
    assert "Test Analytics" in client.messages[1]["text"]


def test_summary_has_plain_language_counts(tmp_path):
    from website_investigator.on_demand import InvestigationResult

    report = tmp_path / "report.html"
    result = InvestigationResult(
        request_id="request-1",
        target_id="site-opaque",
        observation=_observation(),
        report_path=report,
        saved_paths=(report,),
    )
    summary = format_slack_summary(result)
    assert "Fullført" in summary
    assert "1 eksternt domene" in summary
    assert "1 informasjonskapsel" in summary
    assert "request-1" in summary


def test_slack_setup_never_writes_tokens_to_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "website_investigator.slack_bridge.verify_slack_tokens",
        lambda app_token, bot_token: ("T_PRIVATE", "Private workspace"),
    )
    stored: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "website_investigator.slack_bridge.store_slack_token",
        lambda kind, value: stored.append((kind, value)),
    )
    monkeypatch.setattr(
        "website_investigator.slack_bridge.install_launch_agent",
        lambda runtime: tmp_path / "agent.plist",
    )

    config, _ = configure_slack(
        tmp_path,
        app_token="xapp-secret-test-value",
        bot_token="xoxb-secret-test-value",
    )

    assert config.enabled
    assert config.workspace_id == "T_PRIVATE"
    assert len(stored) == 2
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file()
    )
    assert "secret-test-value" not in runtime_text
    assert load_slack_config(tmp_path).workspace_id == "T_PRIVATE"


def test_launch_agent_contains_no_credentials(tmp_path):
    payload = render_launch_agent(tmp_path, Path("/opt/wi/bin/python"))
    assert b"xapp-" not in payload
    assert b"xoxb-" not in payload
    assert b"website_investigator" in payload
    assert str(tmp_path).encode() in payload


def test_keychain_write_does_not_put_token_in_process_arguments(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("website_investigator.slack_bridge.sys.platform", "darwin")
    monkeypatch.setattr("website_investigator.slack_bridge.subprocess.run", fake_run)
    store_slack_token("app-token", "xapp-private-value")

    assert "xapp-private-value" not in captured["arguments"]
    assert captured["arguments"][-1] == "-w"
    assert captured["input"] == "xapp-private-value\n"


def test_public_slack_manifest_has_only_required_scopes():
    import yaml

    manifest_path = Path(__file__).resolve().parents[1] / "slack-app-manifest.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["settings"]["socket_mode_enabled"] is False
    command = manifest["features"]["slash_commands"][0]
    assert command["command"] == "/undersok"
    assert command["url"].endswith("/slack/commands")
    assert set(manifest["oauth_config"]["scopes"]["bot"]) == {
        "commands",
        "chat:write",
        "files:write",
    }
