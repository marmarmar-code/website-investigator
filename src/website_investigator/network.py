from __future__ import annotations

import hashlib
import socket
import ssl
from urllib.parse import urlparse

import dns.exception
import dns.resolver

from .models import TLSObservation
from .safety import UnsafeTargetError, resolve_public_addresses, validate_public_url

DNS_TYPES = ("A", "AAAA", "CNAME", "NS", "MX", "TXT")


def inspect_dns(host: str, timeout: float = 5.0) -> tuple[dict[str, list[str]], list[str]]:
    errors: list[str] = []
    records: dict[str, list[str]] = {}
    try:
        resolve_public_addresses(host, 443)
    except UnsafeTargetError as exc:
        return records, [f"DNS safety check failed: {exc}"]

    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = timeout
    resolver.lifetime = timeout
    for record_type in DNS_TYPES:
        try:
            answers = resolver.resolve(host, record_type, raise_on_no_answer=False)
            if answers.rrset is None:
                continue
            values: list[str] = []
            for answer in answers:
                value = answer.to_text().strip()
                if record_type == "TXT":
                    value = value.strip('"').replace('" "', "")
                values.append(value)
            if values:
                records[record_type] = sorted(set(values))
        except (
            dns.resolver.NoNameservers,
            dns.resolver.NXDOMAIN,
            dns.exception.DNSException,
        ) as exc:
            if record_type in {"A", "AAAA"}:
                errors.append(f"DNS {record_type}: {type(exc).__name__}")
    return records, errors


def _flatten_name(parts: tuple[tuple[tuple[str, str], ...], ...] | tuple) -> str | None:
    flattened: list[str] = []
    for group in parts or ():
        for key, value in group:
            flattened.append(f"{key}={value}")
    return ", ".join(flattened) or None


def inspect_tls(url: str, timeout: float = 8.0) -> TLSObservation:
    try:
        normalized = validate_public_url(url)
        parsed = urlparse(normalized)
        if parsed.scheme != "https":
            return TLSObservation(available=False, error="Target is not HTTPS")
        host = parsed.hostname or ""
        port = parsed.port or 443
        resolve_public_addresses(host, port)

        context = ssl.create_default_context()
        with (
            socket.create_connection((host, port), timeout=timeout) as raw_socket,
            context.wrap_socket(raw_socket, server_hostname=host) as tls_socket,
        ):
            certificate = tls_socket.getpeercert()
            binary = tls_socket.getpeercert(binary_form=True)

        san = sorted(
            value
            for kind, value in certificate.get("subjectAltName", ())
            if kind == "DNS"
        )
        return TLSObservation(
            available=True,
            issuer=_flatten_name(certificate.get("issuer", ())),
            subject=_flatten_name(certificate.get("subject", ())),
            serial_number=certificate.get("serialNumber"),
            not_before=certificate.get("notBefore"),
            not_after=certificate.get("notAfter"),
            san=san,
            sha256_fingerprint=hashlib.sha256(binary).hexdigest() if binary else None,
        )
    except (OSError, ssl.SSLError, UnsafeTargetError, ValueError) as exc:
        return TLSObservation(available=False, error=str(exc))
