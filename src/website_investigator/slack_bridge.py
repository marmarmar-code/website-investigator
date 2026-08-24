from __future__ import annotations

import html
import logging
import os
import plistlib
import queue
import subprocess
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from .models import SlackRuntimeConfig
from .on_demand import (
    InvestigationResult,
    private_repository_is_clean,
    run_on_demand_investigation,
    sync_private_paths,
)

LOGGER = logging.getLogger(__name__)
KEYCHAIN_SERVICE = "no.medier24.website-investigator.slack"
LAUNCH_AGENT_LABEL = "no.medier24.website-investigator.slack"
CATEGORY_LABELS = {
    "publishing_platform": "Publisering",
    "paywall": "Betaling og abonnement",
    "advertising": "Annonsering",
    "analytics": "Måling og analyse",
    "consent": "Samtykke og personvern",
    "infrastructure": "Infrastruktur",
}


class SlackClient(Protocol):
    def chat_postMessage(self, **kwargs: Any) -> Any: ...

    def files_upload_v2(self, **kwargs: Any) -> Any: ...


@dataclass(slots=True)
class SlackJob:
    request_id: str
    url: str
    user_id: str
    team_id: str
    channel_id: str


def load_slack_config(runtime: Path) -> SlackRuntimeConfig:
    path = runtime.resolve() / "config" / "slack.yml"
    if not path.exists():
        return SlackRuntimeConfig()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SlackRuntimeConfig.model_validate(payload)


def write_slack_config(runtime: Path, config: SlackRuntimeConfig) -> Path:
    path = runtime.resolve() / "config" / "slack.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        yaml.safe_dump(
            config.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def parse_command_text(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].split("|", 1)[0]
    if not value or value.lower() in {"help", "hjelp"}:
        raise ValueError("Bruk /undersok nettadresse.no")
    if any(character.isspace() for character in value):
        raise ValueError("Oppgi én nettadresse, for eksempel /undersok nettadresse.no")
    if len(value) > 2048:
        raise ValueError("Nettadressen er for lang")
    return value


def is_authorized(
    config: SlackRuntimeConfig,
    *,
    team_id: str,
    user_id: str,
    channel_id: str,
    connected_team_id: str,
) -> bool:
    if not config.enabled or not team_id or team_id != connected_team_id:
        return False
    if config.workspace_id and team_id != config.workspace_id:
        return False
    if config.allowed_user_ids and user_id not in config.allowed_user_ids:
        return False
    return not config.allowed_channel_ids or channel_id in config.allowed_channel_ids


def _slack_escape(value: str) -> str:
    return html.escape(value, quote=False).replace("&#x27;", "'")


def _count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def format_slack_summary(result: InvestigationResult) -> str:
    observation = result.observation
    status = {
        "success": "Fullført",
        "partial": "Fullført med forbehold",
        "failed": "Kunne ikke fullføres",
    }[observation.status]
    host = _slack_escape(observation.host or "ukjent nettsted")
    lines = [f"*Undersøkelse ferdig: {host}*", f"Status: {status}"]

    if observation.findings:
        lines.append("\n*Viktigste funn*")
        confidence = {
            "strong": "høy sikkerhet",
            "likely": "middels sikkerhet",
            "weak": "lav sikkerhet",
        }
        for finding in sorted(
            observation.findings,
            key=lambda item: (item.score, item.name.lower()),
            reverse=True,
        )[:8]:
            category = CATEGORY_LABELS.get(finding.category, "Annet")
            lines.append(
                f"• {category}: {_slack_escape(finding.name)} "
                f"({confidence.get(finding.confidence, finding.confidence)})"
            )
    else:
        lines.append("\nIngen navngitte teknologifunn ble identifisert.")

    lines.extend(
        [
            "\n*Omfang*",
            "• "
            + _count_label(
                len(observation.third_party_domains),
                "eksternt domene",
                "eksterne domener",
            ),
            "• "
            + _count_label(
                len(observation.cookie_names),
                "informasjonskapsel",
                "informasjonskapsler",
            ),
            "• "
            + _count_label(
                len(observation.errors),
                "teknisk forbehold",
                "tekniske forbehold",
            ),
            f"\nReferanse: `{result.request_id}`",
            "Fullrapporten følger som en privat HTML-fil.",
        ]
    )
    if observation.ads_txt.available:
        lines.insert(
            -3,
            "• "
            + _count_label(
                len(observation.ads_txt.entries),
                "oppføring i ads.txt",
                "oppføringer i ads.txt",
            ),
        )
    if observation.security_txt.contacts:
        lines.insert(
            -3,
            "• "
            + _count_label(
                len(observation.security_txt.contacts),
                "sikkerhetskontakt",
                "sikkerhetskontakter",
            ),
        )
    return "\n".join(lines)


def _response_value(response: Any, key: str, default: str) -> str:
    try:
        value = response[key]
    except (KeyError, TypeError):
        value = getattr(response, key, None)
    return str(value) if value else default


def process_slack_job(
    client: SlackClient,
    runtime: Path,
    config: SlackRuntimeConfig,
    job: SlackJob,
) -> InvestigationResult:
    started = client.chat_postMessage(
        channel=job.user_id,
        text=(
            "Website Investigator har startet undersøkelsen. "
            f"Referanse: `{job.request_id}`."
        ),
        unfurl_links=False,
        unfurl_media=False,
    )
    direct_channel = _response_value(started, "channel", job.user_id)
    thread_ts = _response_value(started, "ts", "")
    clean_before = (
        private_repository_is_clean(runtime) if config.sync_private_repository else False
    )

    try:
        result = run_on_demand_investigation(
            runtime,
            job.url,
            source="slack",
            requested_by=job.user_id,
            request_context={"team_id": job.team_id, "channel_id": job.channel_id},
            deep=config.scan_mode == "deep",
            request_id=job.request_id,
        )
    except Exception as exc:
        LOGGER.warning(
            "Slack investigation failed before a report was produced: %s",
            type(exc).__name__,
        )
        client.chat_postMessage(
            channel=direct_channel,
            thread_ts=thread_ts or None,
            text=(
                "Undersøkelsen stoppet før en rapport kunne lages. "
                f"Referanse: `{job.request_id}`."
            ),
            unfurl_links=False,
            unfurl_media=False,
        )
        raise

    client.chat_postMessage(
        channel=direct_channel,
        thread_ts=thread_ts or None,
        text=format_slack_summary(result),
        unfurl_links=False,
        unfurl_media=False,
    )
    try:
        client.files_upload_v2(
            channel=direct_channel,
            thread_ts=thread_ts or None,
            file=str(result.report_path),
            filename=f"website-investigator-{result.request_id}.html",
            title=f"Website Investigator {result.request_id}",
            initial_comment="Full privat rapport",
        )
    except Exception as exc:
        LOGGER.warning("Slack report upload failed: %s", type(exc).__name__)
        client.chat_postMessage(
            channel=direct_channel,
            thread_ts=thread_ts or None,
            text="Rapporten er lagret privat, men Slack klarte ikke å legge ved filen.",
        )

    if config.sync_private_repository:
        sync = sync_private_paths(
            runtime,
            result.saved_paths,
            commit_message=f"Record Slack investigation {result.request_id}",
            clean_before_write=clean_before,
        )
        if sync.status not in {"synced", "unchanged"}:
            client.chat_postMessage(
                channel=direct_channel,
                thread_ts=thread_ts or None,
                text=(
                    "Rapporten er lagret på Macen, men ble ikke synkronisert til "
                    "det private arkivet."
                ),
            )
    return result


class SlackJobWorker:
    def __init__(
        self,
        client: SlackClient,
        runtime: Path,
        config: SlackRuntimeConfig,
    ) -> None:
        self.client = client
        self.runtime = runtime.resolve()
        self.config = config
        self.jobs: queue.Queue[SlackJob | None] = queue.Queue(maxsize=config.queue_size)
        self.thread = threading.Thread(
            target=self._run,
            name="website-investigator-slack-worker",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def submit(self, job: SlackJob) -> bool:
        try:
            self.jobs.put_nowait(job)
        except queue.Full:
            return False
        return True

    def stop(self) -> None:
        with suppress(queue.Full):
            self.jobs.put_nowait(None)
        self.thread.join(timeout=10)

    def _run(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            try:
                process_slack_job(self.client, self.runtime, self.config, job)
            except Exception:
                # The user received a redacted failure message in process_slack_job.
                pass
            finally:
                self.jobs.task_done()


def _keychain_account(token_kind: str) -> str:
    if token_kind not in {"app-token", "bot-token"}:
        raise ValueError("Unknown Slack token kind")
    return token_kind


def read_slack_token(token_kind: str) -> str | None:
    account = _keychain_account(token_kind)
    environment_name = {
        "app-token": "WI_SLACK_APP_TOKEN",
        "bot-token": "WI_SLACK_BOT_TOKEN",
    }[account]
    if value := os.environ.get(environment_name):
        return value.strip()
    if sys.platform != "darwin":
        return None
    completed = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            account,
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def store_slack_token(token_kind: str, value: str) -> None:
    account = _keychain_account(token_kind)
    if sys.platform != "darwin":
        raise RuntimeError("Secure automatic setup currently requires macOS Keychain")
    completed = subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            account,
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
        input=value + "\n",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError("Could not save the Slack credential in macOS Keychain")


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def render_launch_agent(runtime: Path, python_executable: Path) -> bytes:
    runtime = runtime.resolve()
    log_dir = runtime / "logs"
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            str(python_executable.resolve()),
            "-m",
            "website_investigator",
            "slack",
            "run",
            "--runtime",
            str(runtime),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "WorkingDirectory": str(runtime),
        "StandardOutPath": str(log_dir / "slack-bridge.stdout.log"),
        "StandardErrorPath": str(log_dir / "slack-bridge.stderr.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "WI_REDACT_LOGS": "1",
        },
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def install_launch_agent(runtime: Path, python_executable: Path | None = None) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("Automatic background operation currently requires macOS")
    runtime = runtime.resolve()
    (runtime / "logs").mkdir(parents=True, exist_ok=True)
    destination = launch_agent_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_bytes(render_launch_agent(runtime, python_executable or Path(sys.executable)))
    temporary.replace(destination)

    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["/bin/launchctl", "bootout", domain, str(destination)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    started = subprocess.run(
        ["/bin/launchctl", "bootstrap", domain, str(destination)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if started.returncode != 0:
        raise RuntimeError("Slack background service could not be started")
    return destination


def local_slack_checks(runtime: Path) -> list[tuple[str, bool, str]]:
    config_path = runtime.resolve() / "config" / "slack.yml"
    checks: list[tuple[str, bool, str]] = []
    try:
        config = load_slack_config(runtime)
        checks.append(("config", config_path.exists(), str(config_path)))
        checks.append(
            (
                "enabled",
                config.enabled,
                (
                    "Slack bridge enabled in private config"
                    if config.enabled
                    else "Slack bridge is not activated yet"
                ),
            )
        )
        checks.append(
            (
                "workspace",
                bool(config.workspace_id),
                (
                    "Private workspace is pinned"
                    if config.workspace_id
                    else "Workspace not pinned yet"
                ),
            )
        )
    except Exception as exc:
        checks.append(("config", False, f"Invalid private Slack config: {type(exc).__name__}"))
    try:
        import slack_bolt  # noqa: F401

        checks.append(("dependency", True, "Slack runtime installed"))
    except ImportError:
        checks.append(("dependency", False, "Install website-investigator[slack]"))
    app_token_present = bool(read_slack_token("app-token"))
    bot_token_present = bool(read_slack_token("bot-token"))
    checks.append(
        (
            "app_token",
            app_token_present,
            "Stored securely" if app_token_present else "Not configured yet",
        )
    )
    checks.append(
        (
            "bot_token",
            bot_token_present,
            "Stored securely" if bot_token_present else "Not configured yet",
        )
    )
    checks.append(
        (
            "background_service",
            launch_agent_path().exists(),
            str(launch_agent_path()),
        )
    )
    return checks


def verify_slack_tokens(app_token: str, bot_token: str) -> tuple[str, str]:
    if not app_token.startswith("xapp-") or not bot_token.startswith("xoxb-"):
        raise ValueError("Slack token types are not valid")
    try:
        from slack_sdk import WebClient
    except ImportError as exc:
        raise RuntimeError("Install website-investigator[slack]") from exc

    auth = WebClient(token=bot_token).auth_test()
    team_id = str(auth.get("team_id") or "")
    team_name = str(auth.get("team") or "Slack workspace")
    if not team_id:
        raise RuntimeError("Slack did not return a workspace ID")
    # Opening a one-time Socket Mode URL verifies the app token and connections:write scope.
    connection = WebClient(token=app_token).apps_connections_open()
    if not connection.get("url"):
        raise RuntimeError("Slack app token could not open Socket Mode")
    return team_id, team_name


def configure_slack(
    runtime: Path,
    *,
    app_token: str,
    bot_token: str,
    start_background_service: bool = True,
) -> tuple[SlackRuntimeConfig, str]:
    runtime = runtime.resolve()
    team_id, team_name = verify_slack_tokens(app_token, bot_token)
    store_slack_token("app-token", app_token)
    store_slack_token("bot-token", bot_token)
    existing = load_slack_config(runtime)
    config = existing.model_copy(update={"enabled": True, "workspace_id": team_id})
    write_slack_config(runtime, config)
    if start_background_service:
        install_launch_agent(runtime)
    return config, team_name


def run_slack_bridge(runtime: Path) -> None:
    runtime = runtime.resolve()
    config = load_slack_config(runtime)
    if not config.enabled:
        raise RuntimeError("Slack bridge is disabled in the private runtime")
    app_token = read_slack_token("app-token")
    bot_token = read_slack_token("bot-token")
    if not app_token or not bot_token:
        raise RuntimeError("Slack credentials are not available")

    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as exc:
        raise RuntimeError("Install website-investigator[slack]") from exc

    logging.basicConfig(level=logging.WARNING)
    app = App(token=bot_token)
    auth = app.client.auth_test()
    connected_team_id = str(auth.get("team_id") or "")
    if not connected_team_id:
        raise RuntimeError("Slack workspace could not be verified")
    worker = SlackJobWorker(app.client, runtime, config)
    worker.start()

    @app.command(config.command)
    def handle_command(ack: Any, command: dict[str, Any]) -> None:
        team_id = str(command.get("team_id") or "")
        user_id = str(command.get("user_id") or "")
        channel_id = str(command.get("channel_id") or "")
        if not is_authorized(
            config,
            team_id=team_id,
            user_id=user_id,
            channel_id=channel_id,
            connected_team_id=connected_team_id,
        ):
            ack(response_type="ephemeral", text="Du har ikke tilgang til denne kommandoen.")
            return
        try:
            url = parse_command_text(str(command.get("text") or ""))
        except ValueError as exc:
            ack(response_type="ephemeral", text=str(exc))
            return
        request_id = _request_id_for_slack()
        accepted = worker.submit(
            SlackJob(
                request_id=request_id,
                url=url,
                user_id=user_id,
                team_id=team_id,
                channel_id=channel_id,
            )
        )
        if not accepted:
            ack(
                response_type="ephemeral",
                text="Køen er full akkurat nå. Prøv igjen om litt.",
            )
            return
        ack(
            response_type="ephemeral",
            text=(
                "Undersøkelsen er mottatt. Resultatet kommer som en privat melding. "
                f"Referanse: `{request_id}`."
            ),
        )

    try:
        SocketModeHandler(app, app_token).start()
    finally:
        worker.stop()


def _request_id_for_slack() -> str:
    from datetime import UTC, datetime
    from uuid import uuid4

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:10]}"
