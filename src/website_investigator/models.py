from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    source: str
    value: str
    detail: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    confidence: Literal["weak", "likely", "strong"]
    score: int = Field(ge=0, le=1000)
    evidence: list[Evidence] = Field(default_factory=list)
    interpretation: str | None = None
    false_positive_note: str | None = None
    identifiers: list[str] = Field(default_factory=list)


class FetchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_url: str
    final_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    sha256: str | None = None
    error: str | None = None


class TLSObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = False
    issuer: str | None = None
    subject: str | None = None
    serial_number: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    san: list[str] = Field(default_factory=list)
    sha256_fingerprint: str | None = None
    error: str | None = None


class RobotsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_agent: str
    allowed_at_root: bool | None = None
    explicit_group: bool = False
    directives: list[str] = Field(default_factory=list)


class MetadataObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    generator: str | None = None
    canonical_url: str | None = None
    feeds: list[str] = Field(default_factory=list)
    sitemaps: list[str] = Field(default_factory=list)
    manifest: str | None = None
    scripts: list[str] = Field(default_factory=list)
    stylesheet_hosts: list[str] = Field(default_factory=list)
    structured_data: dict[str, Any] = Field(default_factory=dict)


class BrowserObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: bool = False
    succeeded: bool = False
    final_url: str | None = None
    request_domains: list[str] = Field(default_factory=list)
    script_urls: list[str] = Field(default_factory=list)
    cookie_names: list[str] = Field(default_factory=list)
    blocked_private_requests: list[str] = Field(default_factory=list)
    error: str | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    methodology_version: str
    engine_version: str
    target_id: str | None = None
    requested_url: str
    final_url: str | None = None
    host: str | None = None
    registrable_domain: str | None = None
    scan_mode: Literal["quick", "deep"] = "quick"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: Literal["success", "partial", "failed"] = "failed"
    fetches: dict[str, FetchRecord] = Field(default_factory=dict)
    selected_headers: dict[str, str] = Field(default_factory=dict)
    cookie_names: list[str] = Field(default_factory=list)
    dns: dict[str, list[str]] = Field(default_factory=dict)
    tls: TLSObservation = Field(default_factory=TLSObservation)
    robots_policies: list[RobotsPolicy] = Field(default_factory=list)
    metadata: MetadataObservation = Field(default_factory=MetadataObservation)
    browser: BrowserObservation = Field(default_factory=BrowserObservation)
    third_party_domains: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ChangeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    target_id: str | None = None
    event_type: str
    category: str
    severity: Literal["info", "low", "medium", "high"]
    summary: str
    old_value: Any = None
    new_value: Any = None
    evidence: list[Evidence] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    methodology_change: bool = False


class TargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    name: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)
    enabled: bool = True
    profile: str = "publisher"
    groups: list[str] = Field(default_factory=list)
    scan_mode: Literal["quick", "deep"] = "quick"
    private_notes: str | None = None


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[TargetConfig] = Field(default_factory=list)
