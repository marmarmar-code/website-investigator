from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from . import METHODOLOGY_VERSION, SCHEMA_VERSION, __version__
from .browser import inspect_in_browser
from .detectors import DetectionContext, load_detector_pack, run_detectors
from .fetch import SafeFetcher
from .metadata import inspect_html
from .models import MetadataObservation, Observation
from .network import inspect_dns, inspect_tls
from .robots import extract_sitemaps, inspect_robots
from .safety import UnsafeTargetError, normalize_url, validate_public_url
from .standards import parse_ads_txt, parse_security_txt
from .util import host_from_url, registrable_domain

STANDARD_ENDPOINTS = {
    "robots": "/robots.txt",
    "security_txt": "/.well-known/security.txt",
    "ads_txt": "/ads.txt",
    "app_ads_txt": "/app-ads.txt",
}

HEADER_ALLOWLIST = {
    "server",
    "via",
    "x-powered-by",
    "cf-ray",
    "x-cache",
    "x-served-by",
    "content-security-policy",
    "permissions-policy",
    "strict-transport-security",
    "x-robots-tag",
    "link",
    "alt-svc",
    "cache-control",
}


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _merge_metadata(
    static: MetadataObservation,
    rendered: MetadataObservation,
) -> MetadataObservation:
    # Pydantic models are intentionally merged conservatively: static source remains canonical,
    # while dynamically discovered lists are added.
    static.scripts = sorted(set(static.scripts) | set(rendered.scripts))
    static.feeds = sorted(set(static.feeds) | set(rendered.feeds))
    static.sitemaps = sorted(set(static.sitemaps) | set(rendered.sitemaps))
    static.stylesheet_hosts = sorted(
        set(static.stylesheet_hosts) | set(rendered.stylesheet_hosts)
    )
    if not static.generator:
        static.generator = rendered.generator
    if not static.canonical_url:
        static.canonical_url = rendered.canonical_url
    if not static.manifest:
        static.manifest = rendered.manifest
    if not static.structured_data and rendered.structured_data:
        static.structured_data = rendered.structured_data
    return static


def scan_website(
    url: str,
    *,
    target_id: str | None = None,
    deep: bool = False,
    detector_pack_path: Path | None = None,
    timeout: float = 15.0,
) -> Observation:
    started = datetime.now(UTC)
    pack = load_detector_pack(detector_pack_path)
    pack_version = str(pack["version"])
    methodology_version = (
        METHODOLOGY_VERSION
        if pack_version == METHODOLOGY_VERSION
        else f"{METHODOLOGY_VERSION}+pack.{pack_version}"
    )
    try:
        requested = normalize_url(url)
    except (UnsafeTargetError, ValueError) as exc:
        observation = Observation(
            schema_version=SCHEMA_VERSION,
            methodology_version=methodology_version,
            engine_version=__version__,
            target_id=target_id,
            requested_url=url.strip() or "<empty>",
            scan_mode="deep" if deep else "quick",
            started_at=started,
            completed_at=datetime.now(UTC),
        )
        observation.errors.append(str(exc))
        return observation
    observation = Observation(
        schema_version=SCHEMA_VERSION,
        methodology_version=methodology_version,
        engine_version=__version__,
        target_id=target_id,
        requested_url=requested,
        scan_mode="deep" if deep else "quick",
        started_at=started,
    )

    try:
        validate_public_url(requested)
    except (UnsafeTargetError, ValueError) as exc:
        observation.errors.append(str(exc))
        observation.completed_at = datetime.now(UTC)
        return observation

    root_headers: dict[str, str] = {}
    root_body = b""
    with SafeFetcher(timeout=timeout) as fetcher:
        root = fetcher.get(requested)
        observation.fetches["root"] = root.record
        root_body = root.body
        root_headers = {str(key).lower(): str(value) for key, value in root.headers.items()}
        observation.cookie_names = root.cookies
        observation.final_url = root.record.final_url or requested
        observation.host = host_from_url(observation.final_url)
        observation.registrable_domain = registrable_domain(observation.host)
        observation.selected_headers = {
            key: value for key, value in root_headers.items() if key in HEADER_ALLOWLIST
        }

        if root.record.error:
            observation.errors.append(f"Root fetch: {root.record.error}")

        if root_body:
            try:
                observation.metadata = inspect_html(root_body, observation.final_url or requested)
            except Exception as exc:
                observation.errors.append(f"HTML metadata: {type(exc).__name__}: {exc}")

        origin = _origin(observation.final_url or requested)
        for name, path in STANDARD_ENDPOINTS.items():
            result = fetcher.get(origin + path)
            observation.fetches[name] = result.record
            if name == "robots" and result.record.status_code == 200 and result.body:
                raw_robots = result.body.decode("utf-8", errors="replace")
                observation.robots_policies = inspect_robots(raw_robots, origin + "/")
                observation.metadata.sitemaps = sorted(
                    set(observation.metadata.sitemaps) | set(extract_sitemaps(raw_robots))
                )
            elif name == "security_txt" and result.record.status_code == 200:
                observation.security_txt = parse_security_txt(result.body)
            elif name == "ads_txt" and result.record.status_code == 200:
                observation.ads_txt = parse_ads_txt(result.body)
            elif name == "app_ads_txt" and result.record.status_code == 200:
                observation.app_ads_txt = parse_ads_txt(result.body)

    if observation.host:
        dns_records, dns_errors = inspect_dns(observation.host)
        observation.dns = dns_records
        observation.errors.extend(dns_errors)
    observation.tls = inspect_tls(observation.final_url or requested)

    detector_html = root_body
    if deep and root_body:
        browser_observation, rendered_html = asyncio.run(
            inspect_in_browser(observation.final_url or requested)
        )
        observation.browser = browser_observation
        if browser_observation.error:
            observation.errors.append(f"Browser: {browser_observation.error}")
        if rendered_html:
            detector_html = rendered_html
            try:
                rendered_metadata = inspect_html(
                    rendered_html,
                    browser_observation.final_url or observation.final_url or requested,
                )
                observation.metadata = _merge_metadata(observation.metadata, rendered_metadata)
            except Exception as exc:
                observation.errors.append(f"Rendered metadata: {type(exc).__name__}: {exc}")
        observation.cookie_names = sorted(
            set(observation.cookie_names) | set(browser_observation.cookie_names)
        )

    request_domains = observation.browser.request_domains
    context = DetectionContext(
        html=detector_html,
        metadata=observation.metadata,
        headers=root_headers,
        cookie_names=observation.cookie_names,
        request_domains=request_domains,
    )
    if detector_html:
        observation.findings = run_detectors(context, pack)

    all_hosts = {
        *(host_from_url(script) for script in observation.metadata.scripts),
        *observation.browser.request_domains,
        *observation.metadata.stylesheet_hosts,
    }
    target_domain = observation.registrable_domain
    third_party: set[str] = set()
    for host in all_hosts:
        if not host:
            continue
        domain = registrable_domain(host)
        if domain and domain != target_domain:
            third_party.add(domain)
    observation.third_party_domains = sorted(third_party)

    root_status = observation.fetches["root"].status_code
    if root_status is not None and 200 <= root_status < 400:
        observation.status = "partial" if observation.errors or not root_body else "success"
    else:
        if root_status is not None and not observation.fetches["root"].error:
            observation.errors.append(f"Root fetch returned HTTP {root_status}")
        observation.status = "failed"
    observation.completed_at = datetime.now(UTC)
    return observation
