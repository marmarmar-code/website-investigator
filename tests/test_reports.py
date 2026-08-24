from datetime import UTC, datetime

from website_investigator.models import AdsEntry, Finding, Observation
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
    assert "Kort fortalt" in html
    assert "Journalistisk oversikt" in html
    assert "Teknisk dokumentasjon og rådata" in html


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

    assert "Måling og analyse" in html
    assert "høy sikkerhet" in html
    assert "Eksempelavisen" in html
    assert "1 oppføring fra 1 selgerdomene" in html
    assert "Se selgerdomenene" in html
    assert "mailto:security@example.com" in html
