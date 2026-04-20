"""DARPA opportunities collector - scrapes from DARPA website and SAM.gov"""
import logging
import re
from typing import Optional
from datetime import datetime
import xml.etree.ElementTree as ET

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from ..utils.playwright_helpers import (
    get_browser_context,
    safe_goto,
    screenshot_on_error,
)
from .base import BaseCollector

logger = logging.getLogger(__name__)


class DarpaCollector(BaseCollector):
    """
    Collector for DARPA solicitations.
    
    Scrapes from:
    1. DARPA website opportunities page (links to SAM.gov)
    2. DARPA RSS feed
    3. SAM.gov API (if API key available)
    """

    source_name = "darpa"
    source_url = "https://www.darpa.mil"
    
    # DARPA organization code on SAM.gov
    SAM_DARPA_ORG = "97AS"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _determine_office(self, text: str) -> str:
        """Determine DARPA office from text"""
        text_upper = text.upper() if text else ""

        offices = {
            "DSO": "Defense Sciences Office",
            "MTO": "Microsystems Technology Office",
            "BTO": "Biological Technologies Office",
            "I2O": "Information Innovation Office",
            "STO": "Strategic Technology Office",
            "STPO": "Space Technology Program Office",
            "TTO": "Tactical Technology Office",
        }

        for abbr, name in offices.items():
            if abbr in text_upper:
                return name

        return "DARPA"

    def _determine_type(self, title: str) -> OpportunityType:
        """Determine opportunity type from title"""
        title_lower = title.lower() if title else ""

        if "baa" in title_lower or "broad agency" in title_lower or "office-wide" in title_lower:
            return OpportunityType.BAA
        elif "rfi" in title_lower or "request for information" in title_lower:
            return OpportunityType.RFI
        elif "sbir" in title_lower:
            return OpportunityType.SBIR
        elif "sttr" in title_lower:
            return OpportunityType.STTR
        elif "challenge" in title_lower or "prize" in title_lower:
            return OpportunityType.OTHER

        return OpportunityType.BAA

    async def _scrape_darpa_website(self) -> list[Opportunity]:
        """Scrape opportunities from DARPA website - extracts SAM.gov links"""
        opportunities = []
        
        try:
            async with get_browser_context() as (browser, context, page):
                url = "https://www.darpa.mil/work-with-us/opportunities"
                self.logger.info(f"Navigating to {url}")
                
                if not await safe_goto(page, url, timeout=30000):
                    return []
                
                await page.wait_for_timeout(3000)
                
                # Find all links to SAM.gov opportunities
                sam_links = await page.query_selector_all("a[href*='sam.gov/opp']")
                self.logger.info(f"Found {len(sam_links)} SAM.gov opportunity links")
                
                for link in sam_links:
                    try:
                        href = await link.get_attribute("href") or ""
                        text = (await link.text_content() or "").strip()
                        
                        if not text or not href:
                            continue
                        
                        # Extract SAM.gov opportunity ID from URL
                        sam_match = re.search(r'sam\.gov/opp/([a-f0-9-]+)/view', href)
                        sam_id = sam_match.group(1) if sam_match else hash(href) % 1000000
                        
                        # Try to get parent element for more context
                        parent = await link.evaluate_handle("el => el.parentElement")
                        parent_text = ""
                        if parent:
                            parent_text = await parent.evaluate("el => el.textContent || ''")
                        
                        opp = Opportunity(
                            source=self.source_name,
                            source_id=f"darpa_{sam_id}",
                            source_url=href,
                            title=text,
                            description=parent_text[:500] if parent_text else "",
                            opportunity_type=self._determine_type(text),
                            status=OpportunityStatus.OPEN,
                            agency="Department of Defense",
                            sub_agency="DARPA",
                            office=self._determine_office(text),
                            raw_data={"source": "darpa_website", "sam_url": href},
                        )
                        opportunities.append(opp)
                        self.logger.info(f"Found: {text[:50]}... -> {href[:50]}...")
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to parse link: {e}")
                        continue
                
                # Also look for other opportunity links (non-SAM.gov)
                other_links = await page.query_selector_all("a[href*='/research/'], a[href*='/program/']")
                for link in other_links[:20]:
                    try:
                        href = await link.get_attribute("href") or ""
                        text = (await link.text_content() or "").strip()
                        
                        if not text or len(text) < 5:
                            continue
                        
                        # Skip navigation
                        skip = ["menu", "nav", "research opportunities", "see all", "view all"]
                        if any(s in text.lower() for s in skip):
                            continue
                        
                        if not href.startswith("http"):
                            href = f"{self.source_url}{href}"
                        
                        opp_id = f"darpa_web_{hash(text) % 100000}"
                        
                        # Avoid duplicates
                        if any(o.source_id == opp_id for o in opportunities):
                            continue
                        
                        opp = Opportunity(
                            source=self.source_name,
                            source_id=opp_id,
                            source_url=href,
                            title=text,
                            description="",
                            opportunity_type=self._determine_type(text),
                            status=OpportunityStatus.OPEN,
                            agency="Department of Defense",
                            sub_agency="DARPA",
                            office=self._determine_office(text),
                            raw_data={"source": "darpa_website"},
                        )
                        opportunities.append(opp)
                        
                    except Exception as e:
                        continue
                        
        except Exception as e:
            self.logger.error(f"Website scraping failed: {e}")
            
        return opportunities

    async def _try_rss_feed(self) -> list[Opportunity]:
        """Fetch opportunities from DARPA RSS feed"""
        opportunities = []

        try:
            async with HttpClient(rate_limit=1.0, timeout=30) as client:
                self.logger.info(f"Fetching RSS feed: {self.config.darpa_rss_url}")
                response = await client.get(self.config.darpa_rss_url)

                if isinstance(response, str):
                    root = ET.fromstring(response)

                    for item in root.findall(".//item"):
                        title_el = item.find("title")
                        link_el = item.find("link")
                        desc_el = item.find("description")
                        pub_date_el = item.find("pubDate")

                        if title_el is None or title_el.text is None:
                            continue

                        title = title_el.text.strip()
                        link = link_el.text.strip() if link_el is not None and link_el.text else ""
                        description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                        pub_date = None

                        if pub_date_el is not None and pub_date_el.text:
                            pub_date = self._normalize_date(pub_date_el.text)

                        opp = Opportunity(
                            source=self.source_name,
                            source_id=f"darpa_rss_{hash(link or title) % 100000}",
                            source_url=link or self.config.darpa_url,
                            title=title,
                            description=description,
                            opportunity_type=self._determine_type(title),
                            status=OpportunityStatus.OPEN,
                            agency="Department of Defense",
                            sub_agency="DARPA",
                            office=self._determine_office(title + " " + description),
                            posted_date=pub_date,
                            raw_data={"source": "rss"},
                        )
                        opportunities.append(opp)

                    self.logger.info(f"RSS feed: {len(opportunities)} opportunities")

        except Exception as e:
            self.logger.warning(f"RSS feed failed: {e}")

        return opportunities

    async def _fetch_from_sam_gov(self) -> list[Opportunity]:
        """Fetch DARPA opportunities from SAM.gov API"""
        opportunities = []
        
        api_key = self.config.sam_gov_api_key
        if not api_key:
            self.logger.info("No SAM.gov API key, skipping API source")
            return []

        try:
            async with HttpClient(rate_limit=0.5, timeout=60) as client:
                params = {
                    "api_key": api_key,
                    "limit": 100,
                    "postedFrom": "01/01/2024",
                    "postedTo": "12/31/2026",
                    "orgCode": self.SAM_DARPA_ORG,
                }
                
                self.logger.info("Fetching from SAM.gov API")
                
                try:
                    response = await client.get(
                        self.config.sam_gov_api_url,
                        params=params,
                    )
                    
                    if isinstance(response, dict):
                        opps_data = response.get("opportunitiesData", [])
                        self.logger.info(f"SAM.gov API: {len(opps_data)} opportunities")
                        
                        for item in opps_data:
                            try:
                                notice_id = item.get("noticeId", "")
                                title = item.get("title", "")
                                
                                if not title:
                                    continue
                                
                                posted_date = self._normalize_date(item.get("postedDate"))
                                response_date = self._normalize_date(item.get("responseDeadLine"))
                                
                                status = OpportunityStatus.OPEN
                                if item.get("active") == "No":
                                    status = OpportunityStatus.CLOSED
                                
                                opp = Opportunity(
                                    source=self.source_name,
                                    source_id=f"darpa_sam_{notice_id}",
                                    source_url=f"https://sam.gov/opp/{notice_id}/view",
                                    solicitation_number=item.get("solicitationNumber", notice_id),
                                    title=title,
                                    description=item.get("description", "")[:2000],
                                    opportunity_type=self._determine_type(title),
                                    status=status,
                                    agency="Department of Defense",
                                    sub_agency="DARPA",
                                    office=self._determine_office(title),
                                    posted_date=posted_date,
                                    close_date=response_date,
                                    response_deadline=response_date,
                                    raw_data={"source": "sam_gov_api"},
                                )
                                opportunities.append(opp)
                                
                            except Exception as e:
                                self.logger.warning(f"Failed to parse SAM.gov item: {e}")
                                
                except Exception as e:
                    self.logger.warning(f"SAM.gov API failed: {e}")
                    
        except Exception as e:
            self.logger.error(f"SAM.gov fetch failed: {e}")
            
        return opportunities

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from all DARPA sources"""
        all_opportunities = []
        
        # Scrape DARPA website (gets SAM.gov links)
        web_opps = await self._scrape_darpa_website()
        all_opportunities.extend(web_opps)
        
        # Try RSS feed
        rss_opps = await self._try_rss_feed()
        all_opportunities.extend(rss_opps)
        
        # Try SAM.gov API if key available
        sam_opps = await self._fetch_from_sam_gov()
        all_opportunities.extend(sam_opps)

        # Deduplicate by title similarity and SAM.gov ID
        seen = set()
        unique = []
        for opp in all_opportunities:
            # Create dedup key from title or SAM ID
            key = opp.title.lower().strip()[:40]
            if "sam.gov/opp/" in opp.source_url:
                # Extract SAM ID for better dedup
                sam_match = re.search(r'sam\.gov/opp/([a-f0-9-]+)', opp.source_url)
                if sam_match:
                    key = sam_match.group(1)
            
            if key not in seen:
                seen.add(key)
                unique.append(opp)

        self.logger.info(f"Collected {len(unique)} unique DARPA opportunities")
        return unique
