from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import tldextract

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def utc_now() -> datetime:
    return datetime.now(UTC)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def truncate(value: str | None, limit: int = 500) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def registrable_domain(hostname: str | None) -> str | None:
    if not hostname:
        return None
    result = _EXTRACT(hostname)
    if not result.domain:
        return hostname.lower().rstrip(".")
    return ".".join(part for part in (result.domain, result.suffix) if part).lower()


def absolute_url(base: str, candidate: str | None) -> str | None:
    if not candidate:
        return None
    try:
        resolved = urljoin(base, candidate.strip())
        parsed = urlparse(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        return resolved
    except ValueError:
        return None


def host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def json_text(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, payload: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json_text(payload)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
