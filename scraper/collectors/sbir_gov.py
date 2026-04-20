"""SBIR.gov API collector"""
import logging
from typing import Optional

from ..config import get_config, SAM_SEARCH_KEYWORDS
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class SbirGovCollector(BaseCollector):
    """
    Collector for SBIR.gov Solicitations API.
    
    Note: This API may be under maintenance. The collector handles failures gracefully.
    """

    source_name = "sbir_gov"
    source_url = "https://www.sbir.gov"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _map_status(self, status: str) -> OpportunityStatus:
        """Map SBIR.gov status to our OpportunityStatus"""
        status_lower = status.lower() if status else ""
        if status_lower in ["open", "accepting applications"]:
            return OpportunityStatus.OPEN
        elif status_lower in ["closed", "closed for applications"]:
            return OpportunityStatus.CLOSED
        elif status_lower == "forecasted":
            return OpportunityStatus.FORECASTED
        return OpportunityStatus.UNKNOWN

    def _map_program_type(self, program: str) -> OpportunityType:
        """Map SBIR.gov program to our OpportunityType"""
        program_lower = program.lower() if program else ""
        if "sbir" in program_lower:
            return OpportunityType.SBIR
        elif "sttr" in program_lower:
            return OpportunityType.STTR
        return OpportunityType.OTHER

    def _parse_solicitation(self, data: dict) -> Optional[Opportunity]:
        """Parse SBIR.gov API response into Opportunity model"""
        try:
            sol_number = data.get("solicitation_number", "")
            sol_title = data.get("solicitation_title", "")

            if not sol_number and not sol_title:
                return None

            source_id = sol_number or str(hash(sol_title))
            source_url = f"https://www.sbir.gov/node/{data.get('nid', '')}" if data.get('nid') else self.source_url

            close_date = self._normalize_date(data.get("close_date"))
            open_date = self._normalize_date(data.get("open_date"))
            release_date = self._normalize_date(data.get("release_date"))

            topics = data.get("solicitation_topics", [])
            description_parts = []
            for topic in topics[:5]:
                topic_title = topic.get("topic_title", "")
                topic_desc = topic.get("topic_description", "")[:500]
                if topic_title:
                    description_parts.append(f"{topic_title}: {topic_desc}")

            description = "\n\n".join(description_parts)

            return Opportunity(
                source=self.source_name,
                source_id=source_id,
                source_url=source_url,
                title=sol_title or f"SBIR/STTR Solicitation {sol_number}",
                description=description,
                opportunity_type=self._map_program_type(data.get("program", "")),
                status=self._map_status(data.get("current_status", "")),
                solicitation_number=sol_number,
                agency=data.get("agency"),
                sub_agency=data.get("branch"),
                office=None,
                posted_date=release_date or open_date,
                close_date=close_date,
                response_deadline=close_date,
                raw_data=data,
            )
        except Exception as e:
            self.logger.error(f"Failed to parse solicitation: {e}")
            return None

    async def _fetch_solicitations(
        self,
        client: HttpClient,
        keyword: Optional[str] = None,
        agency: str = "DOD",
        open_only: bool = True,
        start: int = 0,
        rows: int = 25,
    ) -> list[dict]:
        """Fetch solicitations from SBIR.gov API"""
        params = {
            "start": start,
            "rows": rows,
        }

        if keyword:
            params["keyword"] = keyword
        if agency:
            params["agency"] = agency
        if open_only:
            params["open"] = "1"

        try:
            response = await client.get(
                self.config.sbir_gov_api_url,
                params=params,
            )

            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("results", response.get("solicitations", []))
            return []
        except Exception as e:
            self.logger.warning(f"SBIR.gov API request failed (API may be under maintenance): {e}")
            return []

    async def collect(self) -> list[Opportunity]:
        """
        Collect opportunities from SBIR.gov.
        
        Note: This API is sometimes under maintenance. Failures are handled gracefully.
        """
        opportunities = []
        seen_ids = set()

        try:
            async with HttpClient(rate_limit=1.0, timeout=30) as client:
                self.logger.info("Fetching open DOD solicitations from SBIR.gov")
                results = await self._fetch_solicitations(
                    client,
                    agency="DOD",
                    open_only=True,
                    rows=50,
                )

                for item in results:
                    sol_num = item.get("solicitation_number", "")
                    if sol_num and sol_num not in seen_ids:
                        seen_ids.add(sol_num)
                        opp = self._parse_solicitation(item)
                        if opp:
                            opportunities.append(opp)

                for keyword in ["arctic", "cold region", "polar"]:
                    self.logger.info(f"Searching SBIR.gov for keyword: {keyword}")
                    results = await self._fetch_solicitations(
                        client,
                        keyword=keyword,
                        open_only=False,
                        rows=25,
                    )

                    for item in results:
                        sol_num = item.get("solicitation_number", "")
                        if sol_num and sol_num not in seen_ids:
                            seen_ids.add(sol_num)
                            opp = self._parse_solicitation(item)
                            if opp:
                                opportunities.append(opp)

        except Exception as e:
            self.logger.warning(f"SBIR.gov collector failed (API may be under maintenance): {e}")
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from SBIR.gov")
        return opportunities
