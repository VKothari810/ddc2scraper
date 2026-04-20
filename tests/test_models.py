"""Tests for data models"""
import pytest
from datetime import datetime

from scraper.models import (
    Opportunity,
    OpportunityType,
    OpportunityStatus,
    RunLog,
)


def test_opportunity_creation():
    """Test creating an Opportunity with minimal fields"""
    opp = Opportunity(
        source="test_source",
        source_id="12345",
        source_url="https://example.com/opp/12345",
        title="Test Opportunity",
    )

    assert opp.source == "test_source"
    assert opp.source_id == "12345"
    assert opp.title == "Test Opportunity"
    assert opp.id is not None
    assert opp.opportunity_type == OpportunityType.OTHER
    assert opp.status == OpportunityStatus.UNKNOWN


def test_opportunity_full_fields():
    """Test creating an Opportunity with all fields"""
    opp = Opportunity(
        source="sam_gov",
        source_id="abc123",
        source_url="https://sam.gov/opp/abc123",
        title="Arctic Research BAA",
        description="Research for cold regions",
        opportunity_type=OpportunityType.BAA,
        status=OpportunityStatus.OPEN,
        solicitation_number="W911NF-24-S-0001",
        agency="Department of Defense",
        sub_agency="U.S. Army",
        office="ERDC-CRREL",
        posted_date=datetime(2024, 1, 1),
        close_date=datetime(2024, 12, 31),
        naics_codes=["541715", "541720"],
        arctic_relevance_score=0.95,
        arctic_relevance_reasoning="Explicitly about arctic research",
        arctic_keywords_found=["arctic", "cold regions", "CRREL"],
    )

    assert opp.opportunity_type == OpportunityType.BAA
    assert opp.status == OpportunityStatus.OPEN
    assert opp.arctic_relevance_score == 0.95
    assert len(opp.naics_codes) == 2
    assert len(opp.arctic_keywords_found) == 3


def test_opportunity_json_serialization():
    """Test that Opportunity can be serialized to JSON"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Test",
        posted_date=datetime(2024, 6, 15),
    )

    data = opp.model_dump(mode="json")

    assert isinstance(data, dict)
    assert data["source"] == "test"
    assert data["posted_date"] is not None


def test_run_log_creation():
    """Test creating a RunLog"""
    log = RunLog()

    assert log.run_id is not None
    assert log.started_at is not None
    assert log.completed_at is None
    assert log.total_opportunities == 0
    assert len(log.collectors_run) == 0


def test_opportunity_type_enum():
    """Test OpportunityType enum values"""
    assert OpportunityType.SBIR.value == "SBIR"
    assert OpportunityType.STTR.value == "STTR"
    assert OpportunityType.BAA.value == "BAA"
    assert OpportunityType.CSO.value == "CSO"


def test_opportunity_status_enum():
    """Test OpportunityStatus enum values"""
    assert OpportunityStatus.OPEN.value == "Open"
    assert OpportunityStatus.CLOSED.value == "Closed"
    assert OpportunityStatus.FORECASTED.value == "Forecasted"
