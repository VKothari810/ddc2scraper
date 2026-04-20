"""SAM.gov Opportunities API collector"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from ..config import get_config, SAM_SEARCH_KEYWORDS, SAM_PROCUREMENT_TYPES
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class SamGovCollector(BaseCollector):
    """Collector for SAM.gov Opportunities API"""

    source_name = "sam_gov"
    source_url = "https://sam.gov"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _map_opportunity_type(self, ptype: str) -> OpportunityType:
        """Map SAM.gov procurement type to our OpportunityType"""
        type_map = {
            "o": OpportunityType.RFP,
            "p": OpportunityType.RFP,
            "k": OpportunityType.RFP,
            "r": OpportunityType.RFI,
            "s": OpportunityType.OTHER,
            "a": OpportunityType.OTHER,
        }
        return type_map.get(ptype.lower(), OpportunityType.OTHER)

    def _map_status(self, active: str) -> OpportunityStatus:
        """Map SAM.gov active status to our OpportunityStatus"""
        if active and active.lower() == "yes":
            return OpportunityStatus.OPEN
        return OpportunityStatus.CLOSED

    def _parse_opportunity(self, data: dict) -> Optional[Opportunity]:
        """Parse SAM.gov API response into Opportunity model"""
        try:
            notice_id = data.get("noticeId", "")
            if not notice_id:
                return None

            ui_link = data.get("uiLink", "")
            if not ui_link:
                ui_link = f"https://sam.gov/opp/{notice_id}/view"

            posted_date = self._normalize_date(data.get("postedDate"))
            response_deadline = self._normalize_date(data.get("responseDeadLine"))

            org_path = data.get("fullParentPathName", "")
            org_parts = org_path.split(".") if org_path else []
            agency = org_parts[0] if org_parts else data.get("department")
            sub_agency = org_parts[1] if len(org_parts) > 1 else data.get("subTier")
            office = org_parts[2] if len(org_parts) > 2 else data.get("office")

            naics = data.get("naicsCode")
            naics_codes = [naics] if naics else []

            description = ""
            desc_link = data.get("description", "")
            if desc_link and isinstance(desc_link, str) and not desc_link.startswith("http"):
                description = desc_link

            return Opportunity(
                source=self.source_name,
                source_id=notice_id,
                source_url=ui_link,
                title=data.get("title", "Untitled"),
                description=description,
                opportunity_type=self._map_opportunity_type(data.get("type", "")),
                status=self._map_status(data.get("active")),
                solicitation_number=data.get("solicitationNumber"),
                agency=agency,
                sub_agency=sub_agency,
                office=office,
                posted_date=posted_date,
                close_date=response_deadline,
                response_deadline=response_deadline,
                naics_codes=naics_codes,
                set_aside=data.get("setAside"),
                raw_data=data,
            )
        except Exception as e:
            self.logger.error(f"Failed to parse opportunity: {e}")
            return None

    async def _search_opportunities(
        self,
        client: HttpClient,
        keyword: Optional[str] = None,
        posted_from: Optional[str] = None,
        posted_to: Optional[str] = None,
        ptype: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Execute a single search against SAM.gov API"""
        params = {
            "api_key": self.config.sam_gov_api_key,
            "limit": limit,
            "offset": offset,
        }

        if posted_from:
            params["postedFrom"] = posted_from
        if posted_to:
            params["postedTo"] = posted_to
        if keyword:
            params["title"] = keyword
        if ptype:
            params["ptype"] = ptype

        try:
            response = await client.get(self.config.sam_gov_api_url, params=params)

            if isinstance(response, dict):
                return response.get("opportunitiesData", [])
            return []
        except Exception as e:
            self.logger.error(f"SAM.gov API request failed: {e}")
            return []

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from SAM.gov"""
        if not self.config.sam_gov_api_key:
            self.logger.error("SAM_GOV_API_KEY not configured")
            return []

        opportunities = []
        seen_ids = set()

        today = datetime.now()
        posted_from = (today - timedelta(days=30)).strftime("%m/%d/%Y")
        posted_to = today.strftime("%m/%d/%Y")

        async with HttpClient(rate_limit=self.config.sam_gov_rate_limit) as client:
            for keyword in SAM_SEARCH_KEYWORDS:
                self.logger.info(f"Searching SAM.gov for keyword: {keyword}")

                offset = 0
                while offset < 500:
                    results = await self._search_opportunities(
                        client,
                        keyword=keyword,
                        posted_from=posted_from,
                        posted_to=posted_to,
                        limit=100,
                        offset=offset,
                    )

                    if not results:
                        break

                    for item in results:
                        notice_id = item.get("noticeId")
                        if notice_id and notice_id not in seen_ids:
                            seen_ids.add(notice_id)
                            opp = self._parse_opportunity(item)
                            if opp:
                                opportunities.append(opp)

                    if len(results) < 100:
                        break
                    offset += 100

            self.logger.info("Searching SAM.gov for recent DOD opportunities")
            for ptype in ["o", "p", "k", "r"]:
                offset = 0
                while offset < 300:
                    results = await self._search_opportunities(
                        client,
                        posted_from=posted_from,
                        posted_to=posted_to,
                        ptype=ptype,
                        limit=100,
                        offset=offset,
                    )

                    if not results:
                        break

                    for item in results:
                        notice_id = item.get("noticeId")
                        org_path = item.get("fullParentPathName", "").upper()
                        dept = item.get("department", "").upper()

                        is_dod = any(
                            kw in org_path or kw in dept
                            for kw in ["DEFENSE", "DOD", "ARMY", "NAVY", "AIR FORCE"]
                        )

                        if notice_id and notice_id not in seen_ids and is_dod:
                            seen_ids.add(notice_id)
                            opp = self._parse_opportunity(item)
                            if opp:
                                opportunities.append(opp)

                    if len(results) < 100:
                        break
                    offset += 100

        self.logger.info(f"Collected {len(opportunities)} opportunities from SAM.gov")
        return opportunities
