from __future__ import annotations

from urllib.parse import urlparse

from .models import BrowserObservation
from .safety import UnsafeTargetError, validate_public_url_async

MAX_RENDERED_BYTES = 5_000_000


async def inspect_in_browser(
    url: str,
    timeout_ms: int = 30_000,
    settle_ms: int = 2_000,
    max_requests: int = 1_500,
) -> tuple[BrowserObservation, bytes | None]:
    observation = BrowserObservation(attempted=True)
    try:
        from playwright.async_api import Route, async_playwright
    except ImportError:
        observation.error = "Playwright is not installed; install website-investigator[deep]"
        return observation, None

    request_domains: set[str] = set()
    script_urls: set[str] = set()
    blocked: set[str] = set()
    request_count = 0

    async def is_safe(request_url: str) -> bool:
        parsed = urlparse(request_url)
        if parsed.scheme in {"data", "blob", "about"}:
            return True
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        try:
            await validate_public_url_async(request_url)
        except (UnsafeTargetError, ValueError):
            return False
        return True

    async def route_handler(route: Route) -> None:
        nonlocal request_count
        request_count += 1
        request_url = route.request.url
        if request_count > max_requests:
            blocked.add("request-limit-exceeded")
            await route.abort("blockedbyclient")
            return
        if not await is_safe(request_url):
            blocked.add(request_url[:500])
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    try:
        await validate_public_url_async(url)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                ignore_https_errors=False,
                service_workers="block",
                user_agent=(
                    "WebsiteInvestigator/0.1 "
                    "(+https://github.com/marmarmar-code/website-investigator)"
                ),
            )
            await context.route("**/*", route_handler)
            page = await context.new_page()

            def record_request(request: object) -> None:
                request_url = getattr(request, "url", "")
                parsed = urlparse(request_url)
                if parsed.hostname:
                    request_domains.add(parsed.hostname.lower())
                if getattr(request, "resource_type", "") == "script" and request_url:
                    script_urls.add(request_url)

            page.on("request", record_request)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(settle_ms)
            rendered = (await page.content()).encode("utf-8", errors="replace")
            if len(rendered) > MAX_RENDERED_BYTES:
                rendered = rendered[:MAX_RENDERED_BYTES]
                observation.error = (
                    f"Rendered HTML exceeded {MAX_RENDERED_BYTES} bytes and was truncated"
                )
            cookies = await context.cookies()
            observation.succeeded = response is not None
            observation.final_url = page.url
            observation.request_domains = sorted(request_domains)
            observation.script_urls = sorted(script_urls)[:1000]
            observation.cookie_names = sorted(
                {str(cookie.get("name")) for cookie in cookies if cookie.get("name")}
            )
            observation.blocked_private_requests = sorted(blocked)[:100]
            await context.close()
            await browser.close()
            return observation, rendered
    except Exception as exc:  # Browser failures must not erase a valid quick scan.
        observation.error = f"{type(exc).__name__}: {exc}"
        observation.request_domains = sorted(request_domains)
        observation.script_urls = sorted(script_urls)[:1000]
        observation.blocked_private_requests = sorted(blocked)[:100]
        return observation, None
