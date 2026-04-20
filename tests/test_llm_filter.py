"""Tests for LLM filter and keyword pre-filtering"""
import pytest

from scraper.models import Opportunity
from scraper.llm_filter import keyword_prefilter


def test_keyword_prefilter_definite_arctic():
    """Test that arctic keywords return 'definite'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Arctic Research Opportunity",
        description="Research on cold regions and polar environments",
    )

    result = keyword_prefilter(opp)
    assert result == "definite"


def test_keyword_prefilter_definite_crrel():
    """Test that CRREL keyword returns 'definite'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="CRREL Cold Weather Testing",
        description="Testing for Army research",
    )

    result = keyword_prefilter(opp)
    assert result == "definite"


def test_keyword_prefilter_definite_permafrost():
    """Test that permafrost keyword returns 'definite'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Infrastructure Study",
        description="Studying effects of permafrost on buildings",
    )

    result = keyword_prefilter(opp)
    assert result == "definite"


def test_keyword_prefilter_maybe_extreme_environment():
    """Test that adjacent keywords return 'maybe'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Extreme Environment Operations",
        description="Research for austere environment deployment",
    )

    result = keyword_prefilter(opp)
    assert result == "maybe"


def test_keyword_prefilter_maybe_northcom():
    """Test that NORTHCOM returns 'maybe'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="NORTHCOM Communications Study",
        description="Communications for northern command operations",
    )

    result = keyword_prefilter(opp)
    assert result == "maybe"


def test_keyword_prefilter_skip():
    """Test that unrelated opportunities return 'skip'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Cybersecurity Training",
        description="Develop training materials for cyber operations",
    )

    result = keyword_prefilter(opp)
    assert result == "skip"


def test_keyword_prefilter_case_insensitive():
    """Test that keyword matching is case insensitive"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="ARCTIC RESEARCH",
        description="POLAR CONDITIONS",
    )

    result = keyword_prefilter(opp)
    assert result == "definite"


def test_keyword_prefilter_alaska():
    """Test that Alaska is considered arctic-relevant"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Alaska Infrastructure",
        description="Building in Alaska conditions",
    )

    result = keyword_prefilter(opp)
    assert result == "definite"


def test_keyword_prefilter_ice():
    """Test that 'ice' keyword returns 'definite'"""
    opp = Opportunity(
        source="test",
        source_id="1",
        source_url="https://test.com",
        title="Ice Navigation Systems",
        description="Systems for icebreaker navigation",
    )

    result = keyword_prefilter(opp)
    assert result == "definite"
