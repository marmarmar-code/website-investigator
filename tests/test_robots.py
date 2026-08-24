from website_investigator.robots import inspect_robots


def test_reports_specific_and_wildcard_crawler_policy():
    raw = """
User-agent: *
Allow: /

User-agent: GPTBot
Disallow: /
"""
    policies = {item.user_agent: item for item in inspect_robots(raw, "https://example.com/")}
    assert policies["GPTBot"].allowed_at_root is False
    assert policies["GPTBot"].explicit_group is True
    assert policies["Google-Extended"].allowed_at_root is True
    assert policies["Google-Extended"].explicit_group is False


def test_comment_does_not_end_a_robots_group():
    raw = """
User-agent: GPTBot
# an explanatory comment inside the group
Disallow: /
"""
    policies = {item.user_agent: item for item in inspect_robots(raw, "https://example.com/")}
    assert policies["GPTBot"].explicit_group is True
    assert policies["GPTBot"].directives == ["Disallow: /"]
