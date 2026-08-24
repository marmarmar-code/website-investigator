import httpx

from website_investigator.fetch import SafeFetcher
from website_investigator.safety import UnsafeTargetError


def test_redirect_destination_is_validated_before_request(monkeypatch):
    requested_urls = []
    validated_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "https://example.org/final"})
        return httpx.Response(200, content=b"ok")

    def validate(url):
        validated_urls.append(url)
        return url

    monkeypatch.setattr("website_investigator.fetch.validate_public_url", validate)
    with SafeFetcher() as fetcher:
        fetcher.client.close()
        fetcher.client = httpx.Client(transport=httpx.MockTransport(handler))
        result = fetcher.get("https://example.com")

    assert result.record.status_code == 200
    assert requested_urls == ["https://example.com", "https://example.org/final"]
    assert "https://example.org/final" in validated_urls


def test_unsafe_redirect_is_never_requested(monkeypatch):
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/metadata"})

    def validate(url):
        if "169.254.169.254" in url:
            raise UnsafeTargetError("blocked metadata address")
        return url

    monkeypatch.setattr("website_investigator.fetch.validate_public_url", validate)
    with SafeFetcher() as fetcher:
        fetcher.client.close()
        fetcher.client = httpx.Client(transport=httpx.MockTransport(handler))
        result = fetcher.get("https://example.com")

    assert result.record.error == "blocked metadata address"
    assert requested_urls == ["https://example.com"]
