from pathlib import Path

import pytest

from website_investigator.detectors import DetectionContext, load_detector_pack, run_detectors
from website_investigator.metadata import inspect_html


def test_curated_detectors_return_evidence_and_identifiers():
    html = Path("tests/fixtures/publisher.html").read_bytes()
    metadata = inspect_html(html, "https://example.com/")
    findings = run_detectors(
        DetectionContext(
            html=html,
            metadata=metadata,
            headers={"server": "cloudflare", "cf-ray": "abc"},
            cookie_names=["OptanonConsent"],
            request_domains=["experience.tinypass.com"],
        ),
        load_detector_pack(),
    )
    by_id = {item.id: item for item in findings}
    assert "cms.wordpress" in by_id
    assert "paywall.piano" in by_id
    assert "analytics.gtm" in by_id
    assert "consent.onetrust" in by_id
    assert "GTM-ABC123" in by_id["analytics.gtm"].identifiers
    assert by_id["paywall.piano"].evidence


def test_public_detector_pack_matches_packaged_rules():
    assert load_detector_pack(Path("detector-packs/publishers.yml")) == load_detector_pack()


def test_detector_pack_rejects_invalid_regex(tmp_path):
    path = tmp_path / "invalid.yml"
    path.write_text(
"""
version: test-invalid-regex
detectors:
  - id: broken
    interpretation: Broken test rule.
    false_positive_note: Test-only rule.
    signals:
      - type: html
        pattern: "["
        weight: 50
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid regex"):
        load_detector_pack(path)
