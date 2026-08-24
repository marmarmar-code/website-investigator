from datetime import UTC, datetime

from website_investigator.models import AdsEntry, Finding, Observation, RobotsPolicy
from website_investigator.reports import render_observation


def test_standalone_report_renders():
    observation = Observation(
        schema_version=1,
        methodology_version="m1",
        engine_version="0.1",
        requested_url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        status="success",
        completed_at=datetime.now(UTC),
    )
    html = render_observation(observation)
    assert 'lang="no"' in html
    assert "Website Investigator" in html
    assert "example.com" in html
    assert "Eksterne tjenester" in html
    assert "Crawlere: tillatt eller blokkert" in html
    assert "Teknisk vedlegg" in html


def test_report_explains_findings_and_public_standard_files():
    observation = Observation(
        schema_version=1,
        methodology_version="m2",
        engine_version="0.4.0",
        requested_url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        status="success",
        completed_at=datetime.now(UTC),
        third_party_domains=["service.example"],
        robots_policies=[
            RobotsPolicy(
                user_agent="ExampleBot",
                allowed_at_root=False,
                explicit_group=True,
                directives=["Disallow: /"],
            )
        ],
        findings=[
            Finding(
                id="analytics.example",
                name="Eksempelanalyse",
                category="analytics",
                confidence="strong",
                score=90,
                interpretation="Nettstedet bruker et analyseverktøy.",
                false_positive_note="Et gammelt skript kan ligge igjen.",
            )
        ],
        metadata={
            "structured_data": {
                "json-ld": [
                    {
                        "@type": "NewsMediaOrganization",
                        "name": "Eksempelavisen",
                        "url": "https://example.com",
                    }
                ]
            }
        },
        ads_txt={
            "available": True,
            "entries": [
                AdsEntry(
                    seller_domain="seller.example",
                    publisher_account_id="account-1",
                    relationship="DIRECT",
                )
            ],
        },
        security_txt={
            "available": True,
            "contacts": ["mailto:security@example.com"],
        },
    )

    html = render_observation(observation)

    assert "service.example" in html
    assert "ExampleBot" in html
    assert "Blokkert" in html
    assert "Måling og analyse" in html
    assert "høy sikkerhet" in html
    assert "1 oppføring fra 1 selgerdomene" in html
    assert "Selgerdomener" in html
    assert "Sikkerhetskontakter</th><td>1" in html
