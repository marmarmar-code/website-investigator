from website_investigator.models import FetchRecord, TLSObservation
from website_investigator.scanner import scan_website


class FailedFetcher:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url):
        from website_investigator.fetch import FetchResult

        return FetchResult(
            record=FetchRecord(
                requested_url=url,
                final_url=url,
                status_code=500,
            ),
            body=b"temporary server error",
        )


def test_server_error_is_a_failed_observation(monkeypatch):
    monkeypatch.setattr("website_investigator.scanner.validate_public_url", lambda value: value)
    monkeypatch.setattr("website_investigator.scanner.SafeFetcher", FailedFetcher)
    monkeypatch.setattr("website_investigator.scanner.inspect_dns", lambda host: ({}, []))
    monkeypatch.setattr(
        "website_investigator.scanner.inspect_tls",
        lambda url: TLSObservation(available=False),
    )

    observation = scan_website("https://example.com")

    assert observation.status == "failed"
    assert "Root fetch returned HTTP 500" in observation.errors


class StandardsFetcher(FailedFetcher):
    def get(self, url):
        from website_investigator.fetch import FetchResult

        bodies = {
            "https://example.com": b"<html><title>Example</title></html>",
            "https://example.com/ads.txt": b"seller.example, account-1, DIRECT",
            "https://example.com/app-ads.txt": b"app-seller.example, app-1, RESELLER",
            "https://example.com/.well-known/security.txt": (
                b"Contact: mailto:security@example.com"
            ),
        }
        body = bodies.get(url, b"")
        status = 200 if url in bodies else 404
        return FetchResult(
            record=FetchRecord(
                requested_url=url,
                final_url=url,
                status_code=status,
            ),
            body=body,
        )


def test_scanner_summarizes_public_standard_files(monkeypatch):
    monkeypatch.setattr("website_investigator.scanner.validate_public_url", lambda value: value)
    monkeypatch.setattr("website_investigator.scanner.SafeFetcher", StandardsFetcher)
    monkeypatch.setattr("website_investigator.scanner.inspect_dns", lambda host: ({}, []))
    monkeypatch.setattr(
        "website_investigator.scanner.inspect_tls",
        lambda url: TLSObservation(available=False),
    )

    observation = scan_website("https://example.com")

    assert observation.status == "success"
    assert observation.ads_txt.entries[0].seller_domain == "seller.example"
    assert observation.app_ads_txt.entries[0].relationship == "RESELLER"
    assert observation.security_txt.contacts == ["mailto:security@example.com"]
