from datetime import UTC, datetime

from website_investigator.diff import compare_observations
from website_investigator.models import Evidence, Finding, Observation


def base_observation() -> Observation:
    return Observation(
        schema_version=1,
        methodology_version="m1",
        engine_version="0.1",
        target_id="target-1",
        requested_url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        status="success",
        completed_at=datetime.now(UTC),
    )


def test_identical_observations_produce_no_events():
    old = base_observation()
    new = Observation.model_validate(old.model_dump(mode="json"))
    assert compare_observations(old, new) == []


def test_new_paywall_produces_high_event_with_evidence():
    old = base_observation()
    new = base_observation()
    new.findings = [
        Finding(
            id="paywall.piano",
            name="Piano",
            category="paywall",
            confidence="strong",
            score=90,
            evidence=[Evidence(kind="script_url", source="script", value="tinypass.com")],
        )
    ]
    events = compare_observations(old, new)
    assert len(events) == 1
    assert events[0].event_type == "technology.added"
    assert events[0].severity == "high"
    assert events[0].evidence


def test_methodology_change_rebaselines_instead_of_claiming_site_change():
    old = base_observation()
    new = base_observation()
    new.methodology_version = "m2"
    events = compare_observations(old, new)
    assert [event.event_type for event in events] == ["methodology.changed"]
    assert events[0].methodology_change is True
