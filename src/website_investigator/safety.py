from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeTargetError(ValueError):
    """Raised when a URL could reach a local or otherwise unsafe network target."""


_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
}


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise UnsafeTargetError("URL is empty")
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeTargetError("Only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("Credentials in URLs are not allowed")
    if not parsed.hostname:
        raise UnsafeTargetError("URL has no hostname")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise UnsafeTargetError("URL has an invalid port") from exc
    return parsed.geturl()


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value.split("%", 1)[0])
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_public_addresses(hostname: str, port: int = 443) -> tuple[str, ...]:
    host = hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise UnsafeTargetError(f"Blocked hostname: {host}")

    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None

    if literal is not None:
        if not _is_public_ip(str(literal)):
            raise UnsafeTargetError(f"Blocked non-public address: {literal}")
        return (str(literal),)

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTargetError(f"Hostname could not be resolved: {host}") from exc

    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise UnsafeTargetError(f"Hostname returned no addresses: {host}")
    blocked = [address for address in addresses if not _is_public_ip(address)]
    if blocked:
        raise UnsafeTargetError(
            f"Hostname resolves to blocked address range: {', '.join(blocked)}"
        )
    return tuple(addresses)


def validate_public_url(url: str) -> str:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve_public_addresses(parsed.hostname or "", port)
    return normalized


async def validate_public_url_async(url: str) -> str:
    return await asyncio.to_thread(validate_public_url, url)
