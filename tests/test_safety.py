import socket

import pytest

from website_investigator.safety import UnsafeTargetError, normalize_url, resolve_public_addresses


def test_normalize_adds_https():
    assert normalize_url("example.com") == "https://example.com"


def test_rejects_credentials():
    with pytest.raises(UnsafeTargetError):
        normalize_url("https://user:pass@example.com")


def test_rejects_invalid_port():
    with pytest.raises(UnsafeTargetError):
        normalize_url("https://example.com:not-a-port")


def test_rejects_localhost():
    with pytest.raises(UnsafeTargetError):
        resolve_public_addresses("localhost")


def test_rejects_private_dns_result(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeTargetError):
        resolve_public_addresses("private.example")


def test_accepts_public_dns_result(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert resolve_public_addresses("example.com") == ("93.184.216.34",)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_rejects_non_public_ip_literals(address):
    with pytest.raises(UnsafeTargetError):
        resolve_public_addresses(address)
