from __future__ import annotations

from collections.abc import Iterable

import extruct
from bs4 import BeautifulSoup

from .models import MetadataObservation
from .util import absolute_url, host_from_url, truncate


def _unique(values: Iterable[str | None], limit: int = 500) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
            if len(output) >= limit:
                break
    return output


def _meta_content(
    soup: BeautifulSoup,
    *,
    name: str | None = None,
    prop: str | None = None,
) -> str | None:
    attrs: dict[str, str] = {}
    if name:
        attrs["name"] = name
    if prop:
        attrs["property"] = prop
    tag = soup.find("meta", attrs=attrs)
    if tag and tag.get("content"):
        return truncate(str(tag.get("content")), 1000)
    return None


def inspect_html(html: bytes, base_url: str) -> MetadataObservation:
    text = html.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")

    title = truncate(soup.title.get_text(" ", strip=True), 500) if soup.title else None
    description = _meta_content(soup, name="description") or _meta_content(
        soup, prop="og:description"
    )
    generator = _meta_content(soup, name="generator")

    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical = absolute_url(base_url, canonical_tag.get("href")) if canonical_tag else None

    feeds: list[str | None] = []
    sitemaps: list[str | None] = []
    manifest: str | None = None
    stylesheet_hosts: set[str] = set()

    for tag in soup.find_all("link"):
        rel_values = tag.get("rel") or []
        if isinstance(rel_values, str):
            rel_values = rel_values.split()
        rels = {str(value).lower() for value in rel_values}
        href = absolute_url(base_url, tag.get("href"))
        type_value = str(tag.get("type") or "").lower()
        if "alternate" in rels and type_value in {
            "application/rss+xml",
            "application/atom+xml",
            "application/feed+json",
        }:
            feeds.append(href)
        if "sitemap" in rels:
            sitemaps.append(href)
        if "manifest" in rels and href:
            manifest = href
        if "stylesheet" in rels and href:
            host = host_from_url(href)
            if host:
                stylesheet_hosts.add(host)

    scripts = _unique(
        absolute_url(base_url, str(tag.get("src")))
        for tag in soup.find_all("script")
        if tag.get("src")
    )

    structured: dict = {}
    try:
        extracted = extruct.extract(
            text,
            base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=True,
        )
        for key, values in extracted.items():
            if values:
                structured[key] = values[:50] if isinstance(values, list) else values
    except (ValueError, TypeError, AttributeError):
        structured = {}

    return MetadataObservation(
        title=title,
        description=description,
        generator=generator,
        canonical_url=canonical,
        feeds=_unique(feeds, 100),
        sitemaps=_unique(sitemaps, 100),
        manifest=manifest,
        scripts=scripts,
        stylesheet_hosts=sorted(stylesheet_hosts),
        structured_data=structured,
    )


def visible_text_sample(html: bytes, limit: int = 100_000) -> str:
    text = html.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return truncate(soup.get_text(" ", strip=True), limit)


def inline_script_sample(html: bytes, limit: int = 500_000) -> str:
    text = html.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    chunks: list[str] = []
    size = 0
    for tag in soup.find_all("script"):
        if tag.get("src"):
            continue
        value = tag.string or tag.get_text(" ", strip=False)
        if not value:
            continue
        remaining = limit - size
        if remaining <= 0:
            break
        chunks.append(value[:remaining])
        size += min(len(value), remaining)
    return "\n".join(chunks)
