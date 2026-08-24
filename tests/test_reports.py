from datetime import UTC, datetime

from website_investigator.models import Observation
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
    assert "Website Investigator" in html
    assert "example.com" in html
    assert "Raw normalized observation" in html
