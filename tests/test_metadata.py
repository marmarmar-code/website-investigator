from pathlib import Path

from website_investigator.metadata import inspect_html


def test_extracts_basic_publishing_metadata():
    html = Path("tests/fixtures/publisher.html").read_bytes()
    result = inspect_html(html, "https://example.com/")
    assert result.generator == "WordPress 6"
    assert result.canonical_url == "https://example.com/story"
    assert "https://example.com/feed.xml" in result.feeds
    assert any("tinypass.com" in value for value in result.scripts)
