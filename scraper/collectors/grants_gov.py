"""Grants.gov API collector"""
import logging
from typing import Optional

from ..config import get_config, SAM_SEARCH_KEYWORDS
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class GrantsGovCollector(BaseCollector):
    """Collector for Grants.gov search2 API"""

    source_name = "grants_gov"
    source_url = "https://grants.gov"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _map_status(self, status: str) -> OpportunityStatus:
        """Map Grants.gov status to our OpportunityStatus"""
        status_lower = status.lower() if status else ""
        if status_lower == "posted":
            return OpportunityStatus.OPEN
        elif status_lower == "forecasted":
            return OpportunityStatus.FORECASTED
        elif status_lower in ["closed", "archived"]:
            return OpportunityStatus.CLOSED
        return OpportunityStatus.UNKNOWN

    def _map_opportunity_type(self, doc_type: str, title: str) -> OpportunityType:
        """Infer opportunity type from document type and title"""
        title_lower = title.lower() if title else ""
        doc_lower = doc_type.lower() if doc_type else ""

        if "sbir" in title_lower:
            return OpportunityType.SBIR
        elif "sttr" in title_lower:
            return OpportunityType.STTR
        elif "baa" in title_lower or "broad agency" in title_lower:
            return OpportunityType.BAA
        elif doc_lower == "grant" or "grant" in title_lower:
            return OpportunityType.GRANT
        return OpportunityType.OTHER

    def _parse_opportunity(self, data: dict) -> Optional[Opportunity]:
        """Parse Grants.gov API response into Opportunity model"""
        try:
            opp_id = str(data.get("id", ""))
            opp_number = data.get("number", "")

            if not opp_id:
                return None

            source_url = f"https://grants.gov/search-results-detail/{opp_id}"

            posted_date = self._normalize_date(data.get("openDate"))
            close_date = self._normalize_date(data.get("closeDate"))

            title = data.get("title", "Untitled")

            return Opportunity(
                source=self.source_name,
                source_id=opp_id,
                source_url=source_url,
                title=title,
                description="",
                opportunity_type=self._map_opportunity_type(
                    data.get("docType", ""), title
                ),
                status=self._map_status(data.get("oppStatus", "")),
                solicitation_number=opp_number,
                agency=data.get("agencyName"),
                sub_agency=None,
                office=None,
                posted_date=posted_date,
                close_date=close_date,
                response_deadline=close_date,
                naics_codes=[],
                raw_data=data,
            )
        except Exception as e:
            self.logger.error(f"Failed to parse opportunity: {e}")
            return None

    async def _search_opportunities(
        self,
        client: HttpClient,
        keyword: Optional[str] = None,
        agencies: Optional[str] = None,
        statuses: str = "posted|forecasted",
        rows: int = 25,
        start_record: int = 0,
    ) -> tuple[list[dict], int]:
        """
        Execute a search against Grants.gov search2 API.
        
        Returns:
            Tuple of (results list, total hit count)
        """
        payload = {
            "rows": rows,
            "startRecordNum": start_record,
            "oppStatuses": statuses,
        }

        if keyword:
            payload["keyword"] = keyword
        if agencies:
            payload["agencies"] = agencies

        try:
            response = await client.post(
                self.config.grants_gov_api_url,
                json_data=payload,
                headers={"Content-Type": "application/json"},
            )

            if isinstance(response, dict):
                data = response.get("data", response)
                hits = data.get("oppHits", [])
                hit_count = data.get("hitCount", len(hits))
                return hits, hit_count
            return [], 0
        except Exception as e:
            self.logger.error(f"Grants.gov API request failed: {e}")
            return [], 0

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from Grants.gov"""
        opportunities = []
        seen_ids = set()

        async with HttpClient(rate_limit=self.config.default_rate_limit) as client:
            for keyword in SAM_SEARCH_KEYWORDS:
                self.logger.info(f"Searching Grants.gov for keyword: {keyword}")

                start_record = 0
                while start_record < 200:
                    results, total = await self._search_opportunities(
                        client,
                        keyword=keyword,
                        rows=25,
                        start_record=start_record,
                    )

                    if not results:
                        break

                    for item in results:
                        opp_id = str(item.get("id", ""))
                        if opp_id and opp_id not in seen_ids:
                            seen_ids.add(opp_id)
                            opp = self._parse_opportunity(item)
                            if opp:
                                opportunities.append(opp)

                    if start_record + len(results) >= total:
                        break
                    start_record += 25

            self.logger.info("Searching Grants.gov for DOD opportunities")
            start_record = 0
            while start_record < 500:
                results, total = await self._search_opportunities(
                    client,
                    agencies="DOD",
                    rows=25,
                    start_record=start_record,
                )

                if not results:
                    break

                for item in results:
                    opp_id = str(item.get("id", ""))
                    if opp_id and opp_id not in seen_ids:
                        seen_ids.add(opp_id)
                        opp = self._parse_opportunity(item)
                        if opp:
                            opportunities.append(opp)

                if start_record + len(results) >= total:
                    break
                start_record += 25

        self.logger.info(f"Collected {len(opportunities)} opportunities from Grants.gov")
        return opportunities
