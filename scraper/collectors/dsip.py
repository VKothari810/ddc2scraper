"""DSIP (DoD SBIR/STTR Innovation Portal) collector"""
import logging
import json
from typing import Optional
from datetime import datetime
from urllib.parse import quote

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class DsipCollector(BaseCollector):
    """
    Collector for DoD SBIR/STTR Innovation Portal (DSIP).
    
    This is the authoritative source for all DoD SBIR/STTR topics.
    Uses the public topics search API.
    """

    source_name = "dsip"
    source_url = "https://www.dodsbirsttr.mil"
    api_url = "https://www.dodsbirsttr.mil/topics/api/public/topics/search"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _determine_type(self, program: str) -> OpportunityType:
        """Determine SBIR vs STTR from program field"""
        program_upper = program.upper() if program else ""
        if "STTR" in program_upper:
            return OpportunityType.STTR
        return OpportunityType.SBIR

    def _determine_component(self, component: str) -> tuple[str, str]:
        """Determine agency and sub-agency from component"""
        component_upper = component.upper() if component else ""
        
        mappings = {
            "ARMY": ("Department of Defense", "U.S. Army"),
            "NAVY": ("Department of Defense", "U.S. Navy"),
            "AF": ("Department of Defense", "U.S. Air Force"),
            "DARPA": ("Department of Defense", "DARPA"),
            "DHA": ("Department of Defense", "Defense Health Agency"),
            "DLA": ("Department of Defense", "Defense Logistics Agency"),
            "DTRA": ("Department of Defense", "Defense Threat Reduction Agency"),
            "MDA": ("Department of Defense", "Missile Defense Agency"),
            "CBD": ("Department of Defense", "Chemical and Biological Defense"),
            "OSD": ("Department of Defense", "Office of Secretary of Defense"),
            "SOCOM": ("Department of Defense", "U.S. Special Operations Command"),
            "DMEA": ("Department of Defense", "Defense Microelectronics Activity"),
            "NGA": ("Department of Defense", "National Geospatial-Intelligence Agency"),
        }

        for key, (agency, sub) in mappings.items():
            if key in component_upper:
                return agency, sub

        return "Department of Defense", component or "DoD"

    def _parse_status(self, status_text: str) -> OpportunityStatus:
        """Parse status from API response"""
        status_lower = status_text.lower() if status_text else ""
        
        if "pre-release" in status_lower or "pre release" in status_lower:
            return OpportunityStatus.FORECASTED
        elif "open" in status_lower:
            return OpportunityStatus.OPEN
        elif "closed" in status_lower:
            return OpportunityStatus.CLOSED
            
        return OpportunityStatus.UNKNOWN

    def _parse_timestamp(self, ts: Optional[int]) -> Optional[datetime]:
        """Parse timestamp (milliseconds) to datetime"""
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(ts / 1000)
        except (ValueError, TypeError, OSError):
            return None

    def _parse_topic(self, data: dict) -> Optional[Opportunity]:
        """Parse a topic from the API response"""
        try:
            topic_code = data.get("finalTopicCode") or data.get("topicCode", "")
            title = data.get("topicTitle", "")
            
            if not topic_code or not title:
                return None

            component = data.get("componentCode", "")
            agency, sub_agency = self._determine_component(component)
            
            open_date = self._parse_timestamp(data.get("topicStartDate"))
            close_date = self._parse_timestamp(data.get("topicEndDate"))
            
            status = self._parse_status(data.get("topicStatus", ""))
            
            solicitation = data.get("solicitationCycleName", "")
            release_num = data.get("releaseNumber", "")
            
            description = data.get("topicDescription", "") or ""
            
            return Opportunity(
                source=self.source_name,
                source_id=topic_code,
                source_url=f"{self.source_url}/topics-app/?topicNum={topic_code}",
                title=title,
                description=description[:2000] if description else "",
                opportunity_type=self._determine_type(data.get("program", "")),
                status=status,
                solicitation_number=topic_code,
                agency=agency,
                sub_agency=sub_agency,
                posted_date=open_date,
                close_date=close_date,
                response_deadline=close_date,
                raw_data={
                    "component": component,
                    "program": data.get("program"),
                    "solicitation": solicitation,
                    "release_number": release_num,
                    "focus_areas": data.get("focusAreas", []),
                    "technology_areas": data.get("technologyAreas", []),
                },
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse topic: {e}")
            return None

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from DSIP API"""
        opportunities = []

        search_params = {
            "searchText": None,
            "components": None,
            "programYear": None,
            "solicitationCycleNames": ["openTopics"],
            "releaseNumbers": [],
            "topicReleaseStatus": [591, 592],  # Open and Pre-Release
            "modernizationPriorities": None,
            "sortBy": "finalTopicCode,asc"
        }

        try:
            async with HttpClient(rate_limit=1.0, timeout=60) as client:
                page = 0
                page_size = 100
                total = None

                while True:
                    params_json = quote(json.dumps(search_params))
                    url = f"{self.api_url}?searchParam={params_json}&size={page_size}&page={page}"
                    
                    self.logger.info(f"Fetching DSIP topics page {page}...")
                    
                    response = await client.get(url)
                    
                    if not isinstance(response, dict):
                        self.logger.error(f"Unexpected response type: {type(response)}")
                        break
                    
                    if total is None:
                        total = response.get("total", 0)
                        self.logger.info(f"Total topics available: {total}")
                    
                    topics_data = response.get("data", [])
                    
                    if not topics_data:
                        break
                    
                    for topic_data in topics_data:
                        opp = self._parse_topic(topic_data)
                        if opp:
                            opportunities.append(opp)
                    
                    if len(opportunities) >= total or len(topics_data) < page_size:
                        break
                    
                    page += 1
                    
                    if page > 20:
                        self.logger.warning("Reached max pages, stopping")
                        break

        except Exception as e:
            self.logger.error(f"DSIP collection failed: {e}")
            import traceback
            traceback.print_exc()
            return opportunities

        self.logger.info(f"Collected {len(opportunities)} topics from DSIP")
        return opportunities
