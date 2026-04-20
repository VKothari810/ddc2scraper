"""Tests for deduplication logic"""
import pytest
from datetime import datetime

from scraper.models import Opportunity, OpportunityType, OpportunityStatus
from scraper.dedup import (
    normalize_solicitation_number,
    generate_dedup_key,
    merge_opportunities,
    deduplicate_opportunities,
)


def test_normalize_solicitation_number():
    """Test solicitation number normalization"""
    assert normalize_solicitation_number("W911NF-24-S-0001") == "W911NF24S0001"
    assert normalize_solicitation_number("W911NF 24 S 0001") == "W911NF24S0001"
    assert normalize_solicitation_number("w911nf-24-s-0001") == "W911NF24S0001"
    assert normalize_solicitation_number(None) is None
    assert normalize_solicitation_number("") is None


def test_generate_dedup_key_with_solicitation():
    """Test dedup key generation with solicitation number"""
    opp = Opportunity(
        source="sam_gov",
        source_id="123",
        source_url="https://test.com",
        title="Test",
        solicitation_number="W911NF-24-S-0001",
    )

    key = generate_dedup_key(opp)
    assert key == "sol:W911NF24S0001"


def test_generate_dedup_key_without_solicitation():
    """Test dedup key generation without solicitation number"""
    opp = Opportunity(
        source="erdcwerx",
        source_id="abc",
        source_url="https://test.com",
        title="Test",
    )

    key = generate_dedup_key(opp)
    assert key == "erdcwerx:abc"


def test_merge_opportunities():
    """Test merging two opportunities"""
    existing = Opportunity(
        source="sam_gov",
        source_id="1",
        source_url="https://sam.gov/1",
        title="Arctic Research",
        description="Short desc",
        solicitation_number="W911NF-24-S-0001",
        agency="DOD",
    )

    new = Opportunity(
        source="grants_gov",
        source_id="2",
        source_url="https://grants.gov/2",
        title="Arctic Research",
        description="This is a much longer description with more details about the research",
        solicitation_number="W911NF-24-S-0001",
        close_date=datetime(2024, 12, 31),
        sub_agency="Army",
    )

    merged = merge_opportunities(existing, new)

    assert merged.source == "sam_gov"
    assert "longer description" in merged.description
    assert merged.close_date == datetime(2024, 12, 31)
    assert merged.sub_agency == "Army"
    assert "grants_gov" in merged.raw_data.get("also_found_on", [])


def test_deduplicate_opportunities():
    """Test deduplicating a list of opportunities"""
    opps = [
        Opportunity(
            source="sam_gov",
            source_id="1",
            source_url="https://sam.gov/1",
            title="Opp 1",
            solicitation_number="SOL-001",
        ),
        Opportunity(
            source="grants_gov",
            source_id="2",
            source_url="https://grants.gov/2",
            title="Opp 1 (same)",
            solicitation_number="SOL-001",
        ),
        Opportunity(
            source="dsip",
            source_id="3",
            source_url="https://dsip.mil/3",
            title="Opp 2",
            solicitation_number="SOL-002",
        ),
    ]

    deduped = deduplicate_opportunities(opps)

    assert len(deduped) == 2

    sol_001 = next(o for o in deduped if "SOL001" in generate_dedup_key(o))
    assert sol_001 is not None


def test_deduplicate_no_duplicates():
    """Test deduplication with no duplicates"""
    opps = [
        Opportunity(
            source="sam_gov",
            source_id="1",
            source_url="https://test.com/1",
            title="Opp 1",
        ),
        Opportunity(
            source="grants_gov",
            source_id="2",
            source_url="https://test.com/2",
            title="Opp 2",
        ),
    ]

    deduped = deduplicate_opportunities(opps)
    assert len(deduped) == 2
