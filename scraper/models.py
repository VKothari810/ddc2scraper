"""Pydantic data models for opportunities"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class OpportunityType(str, Enum):
    RFP = "RFP"
    RFI = "RFI"
    SBIR = "SBIR"
    STTR = "STTR"
    BAA = "BAA"
    CSO = "CSO"
    OTA = "OTA"
    GRANT = "Grant"
    OTHER = "Other"


class OpportunityStatus(str, Enum):
    OPEN = "Open"
    CLOSED = "Closed"
    FORECASTED = "Forecasted"
    UNKNOWN = "Unknown"


class Opportunity(BaseModel):
    """Unified data model for all opportunity sources"""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    source_id: str
    source_url: str

    # Core fields
    title: str
    description: str = ""
    opportunity_type: OpportunityType = OpportunityType.OTHER
    status: OpportunityStatus = OpportunityStatus.UNKNOWN
    solicitation_number: Optional[str] = None

    # Agency info
    agency: Optional[str] = None
    sub_agency: Optional[str] = None
    office: Optional[str] = None

    # Dates
    posted_date: Optional[datetime] = None
    close_date: Optional[datetime] = None
    response_deadline: Optional[datetime] = None

    # Classification
    naics_codes: list[str] = Field(default_factory=list)
    set_aside: Optional[str] = None

    # Financial
    award_floor: Optional[float] = None
    award_ceiling: Optional[float] = None

    # Arctic relevance (populated by LLM filter)
    arctic_relevance_score: float = 0.0
    arctic_relevance_reasoning: str = ""
    arctic_keywords_found: list[str] = Field(default_factory=list)

    # Metadata
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    raw_data: dict = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class RunLog(BaseModel):
    """Metadata about a scraper run"""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    collectors_run: list[str] = Field(default_factory=list)
    collector_results: dict[str, dict] = Field(default_factory=dict)
    total_opportunities: int = 0
    arctic_opportunities: int = 0
    errors: list[str] = Field(default_factory=list)
