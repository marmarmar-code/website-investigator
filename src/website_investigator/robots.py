from __future__ import annotations

import re

from protego import Protego

from .models import RobotsPolicy

DEFAULT_CRAWLERS = [
    "*",
    "GPTBot",
    "ChatGPT-User",
    "Google-Extended",
    "ClaudeBot",
    "PerplexityBot",
    "CCBot",
]


def _groups(raw: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    current_agents: list[str] = []
    directives_started = False

    for original_line in raw.splitlines():
        if not original_line.strip():
            current_agents = []
            directives_started = False
            continue
        line = original_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key_lower = key.lower()
        if key_lower == "user-agent":
            if directives_started:
                current_agents = []
                directives_started = False
            agent = value
            if agent:
                current_agents.append(agent)
                groups.setdefault(agent.lower(), [])
            continue
        if current_agents and key_lower in {"allow", "disallow", "crawl-delay", "sitemap"}:
            directives_started = True
            rendered = f"{key}: {value}"
            for agent in current_agents:
                groups.setdefault(agent.lower(), []).append(rendered)
    return groups


def inspect_robots(
    raw: str,
    root_url: str,
    crawlers: list[str] | None = None,
) -> list[RobotsPolicy]:
    if not raw.strip():
        return []
    parser = Protego.parse(raw)
    groups = _groups(raw)
    results: list[RobotsPolicy] = []
    for crawler in crawlers or DEFAULT_CRAWLERS:
        try:
            allowed = parser.can_fetch(root_url, crawler)
        except Exception:  # Protego should not make a whole scan fail on malformed input.
            allowed = None
        key = crawler.lower()
        explicit = key in groups
        directives = groups.get(key, [])
        if not explicit and "*" in groups:
            directives = groups["*"]
        results.append(
            RobotsPolicy(
                user_agent=crawler,
                allowed_at_root=allowed,
                explicit_group=explicit,
                directives=directives[:50],
            )
        )
    return results


def extract_sitemaps(raw: str) -> list[str]:
    values: set[str] = set()
    for line in raw.splitlines():
        match = re.match(r"^\s*Sitemap\s*:\s*(\S+)", line, flags=re.IGNORECASE)
        if match:
            values.add(match.group(1))
    return sorted(values)
