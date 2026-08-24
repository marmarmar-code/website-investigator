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
