from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from .models import FetchRecord
from .safety import UnsafeTargetError, validate_public_url
from .util import sha256_bytes

USER_AGENT = (
    "WebsiteInvestigator/0.1 "
    "(+https://github.com/marmarmar-code/website-investigator)"
)
MAX_RESPONSE_BYTES = 5_000_000
MAX_REDIRECTS = 8


@dataclass(slots=True)
class FetchResult:
    record: FetchRecord
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)


class SafeFetcher:
    def __init__(self, timeout: float = 15.0, max_bytes: int = MAX_RESPONSE_BYTES) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,text/plain,"
                    "application/xml;q=0.9,*/*;q=0.5"
                ),
            },
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> SafeFetcher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, url: str) -> FetchResult:
        original = validate_public_url(url)
        current = original
        visited: set[str] = set()

        for _ in range(MAX_REDIRECTS + 1):
            if current in visited:
                return self._error(original, current, "Redirect loop detected")
            visited.add(current)
            try:
                validate_public_url(current)
                with self.client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            return self._from_response(original, current, response, b"")
                        next_url = urljoin(current, location)
                        # Validate every redirect destination before requesting it.
                        validate_public_url(next_url)
                        current = next_url
                        continue

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_bytes:
                            return self._error(
                                original,
                                str(response.url),
                                f"Response exceeded {self.max_bytes} bytes",
                                status=response.status_code,
                            )
                    return self._from_response(original, str(response.url), response, bytes(body))
            except (httpx.HTTPError, UnsafeTargetError, ValueError) as exc:
                return self._error(original, current, str(exc))

        return self._error(original, current, f"More than {MAX_REDIRECTS} redirects")

    @staticmethod
    def _cookie_names(headers: httpx.Headers) -> list[str]:
        names: set[str] = set()
        for value in headers.get_list("set-cookie"):
            pair = value.split(";", 1)[0]
            if "=" in pair:
                name = pair.split("=", 1)[0].strip()
                if name:
                    names.add(name)
        return sorted(names, key=str.lower)

    def _from_response(
        self,
        original: str,
        final_url: str,
        response: httpx.Response,
        body: bytes,
    ) -> FetchResult:
        return FetchResult(
            record=FetchRecord(
                requested_url=original,
                final_url=final_url,
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                content_length=len(body),
                sha256=sha256_bytes(body),
            ),
            body=body,
            headers=dict(response.headers),
            cookies=self._cookie_names(response.headers),
        )

    @staticmethod
    def _error(
        original: str,
        final_url: str | None,
        error: str,
        status: int | None = None,
    ) -> FetchResult:
        return FetchResult(
            record=FetchRecord(
                requested_url=original,
                final_url=final_url,
                status_code=status,
                error=error,
            )
        )
