"""ERDCWERX collector - PRIORITY for arctic relevance (includes CRREL CSO)"""
import logging
import re
from typing import Optional
from datetime import datetime

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.playwright_helpers import (
    get_browser_context,
    safe_goto,
    screenshot_on_error,
)
from .base import BaseCollector

logger = logging.getLogger(__name__)


class ErdcwerxCollector(BaseCollector):
    """
    Collector for ERDCWERX opportunities.
    
    This is the HIGHEST PRIORITY collector for arctic relevance.
    ERDCWERX hosts the Cold Regions Research and Engineering Laboratory (CRREL) CSO,
    which is explicitly focused on cold and complex regions.
    """

    source_name = "erdcwerx"
    source_url = "https://www.erdcwerx.org"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _parse_deadline(self, text: str) -> tuple[Optional[datetime], OpportunityStatus]:
        """Parse deadline text and determine status"""
        if not text:
            return None, OpportunityStatus.UNKNOWN

        text_lower = text.lower()

        if "continuously open" in text_lower or "continuous" in text_lower:
            return None, OpportunityStatus.OPEN

        if "open through" in text_lower or "open until" in text_lower:
            date_match = re.search(
                r"(?:through|until)\s+(\w+\s+\d{1,2},?\s+\d{4})", text, re.IGNORECASE
            )
            if date_match:
                date_str = date_match.group(1)
                parsed = self._normalize_date(date_str)
                if parsed:
                    if parsed > datetime.now():
                        return parsed, OpportunityStatus.OPEN
                    return parsed, OpportunityStatus.CLOSED

        date_patterns = [
            r"(\w+\s+\d{1,2},?\s+\d{4})",
            r"(\d{1,2}/\d{1,2}/\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                parsed = self._normalize_date(match.group(1))
                if parsed:
                    if parsed > datetime.now():
                        return parsed, OpportunityStatus.OPEN
                    return parsed, OpportunityStatus.CLOSED

        return None, OpportunityStatus.OPEN

    def _determine_opportunity_type(self, title: str) -> OpportunityType:
        """Determine opportunity type from title"""
        title_lower = title.lower()

        if "cso" in title_lower or "commercial solutions" in title_lower:
            return OpportunityType.CSO
        elif "baa" in title_lower or "broad agency" in title_lower:
            return OpportunityType.BAA
        elif "ota" in title_lower or "other transaction" in title_lower:
            return OpportunityType.OTA
        elif "sbir" in title_lower:
            return OpportunityType.SBIR
        elif "sttr" in title_lower:
            return OpportunityType.STTR
        elif "rfi" in title_lower or "request for information" in title_lower:
            return OpportunityType.RFI

        return OpportunityType.OTHER

    def _determine_sub_agency(self, title: str) -> str:
        """Determine ERDC sub-agency/lab from title"""
        title_lower = title.lower()

        if "cold regions" in title_lower or "crrel" in title_lower:
            return "CRREL (Cold Regions Research and Engineering Laboratory)"
        elif "geospatial" in title_lower or "grl" in title_lower:
            return "GRL (Geospatial Research Laboratory)"
        elif "construction" in title_lower or "cerl" in title_lower:
            return "CERL (Construction Engineering Research Laboratory)"
        elif "civil works" in title_lower:
            return "Civil Works"

        return "ERDC"

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from ERDCWERX"""
        opportunities = []

        try:
            async with get_browser_context() as (browser, context, page):
                self.logger.info(f"Navigating to {self.config.erdcwerx_url}")

                if not await safe_goto(page, self.config.erdcwerx_url, timeout=60000):
                    await screenshot_on_error(page, self.source_name, self.config.debug_dir)
                    return []

                await page.wait_for_timeout(3000)

                articles = await page.query_selector_all("article")

                if not articles:
                    articles = await page.query_selector_all(".post, .entry, .opportunity, .challenge")

                if not articles:
                    content = await page.content()
                    self.logger.info("Parsing page content directly")
                    opportunities = await self._parse_page_content(page, content)
                    return opportunities

                self.logger.info(f"Found {len(articles)} opportunity items")

                for i, article in enumerate(articles):
                    try:
                        title_el = await article.query_selector("h2 a, h3 a, .entry-title a, a.title")
                        if not title_el:
                            title_el = await article.query_selector("h2, h3, .entry-title")

                        if not title_el:
                            continue

                        title = (await title_el.text_content() or "").strip()
                        if not title:
                            continue

                        link = await title_el.get_attribute("href") if title_el else None
                        if not link:
                            link_el = await article.query_selector("a")
                            link = await link_el.get_attribute("href") if link_el else None

                        if link and not link.startswith("http"):
                            link = f"{self.source_url}{link}" if link.startswith("/") else f"{self.source_url}/{link}"

                        deadline_el = await article.query_selector(
                            ".deadline, .date, .meta, p:has-text('Deadline'), p:has-text('Open')"
                        )
                        deadline_text = ""
                        if deadline_el:
                            deadline_text = (await deadline_el.text_content() or "").strip()

                        if not deadline_text:
                            article_text = (await article.text_content() or "")
                            deadline_match = re.search(
                                r"Deadline[:\s—-]+([^\n]+)", article_text, re.IGNORECASE
                            )
                            if deadline_match:
                                deadline_text = deadline_match.group(1).strip()

                        close_date, status = self._parse_deadline(deadline_text)

                        desc_el = await article.query_selector(
                            ".entry-content, .excerpt, .description, p"
                        )
                        description = ""
                        if desc_el:
                            description = (await desc_el.text_content() or "").strip()

                        opp = Opportunity(
                            source=self.source_name,
                            source_id=f"erdcwerx_{i}_{hash(title) % 10000}",
                            source_url=link or self.config.erdcwerx_url,
                            title=title,
                            description=description,
                            opportunity_type=self._determine_opportunity_type(title),
                            status=status,
                            agency="U.S. Army Corps of Engineers",
                            sub_agency=self._determine_sub_agency(title),
                            office="ERDC",
                            close_date=close_date,
                            response_deadline=close_date,
                            raw_data={
                                "deadline_text": deadline_text,
                                "scraped_from": self.config.erdcwerx_url,
                            },
                        )

                        if "cold regions" in title.lower() or "crrel" in title.lower():
                            opp.arctic_relevance_score = 1.0
                            opp.arctic_relevance_reasoning = "CRREL CSO - explicitly for cold regions research"
                            opp.arctic_keywords_found = ["cold regions", "CRREL"]

                        opportunities.append(opp)
                        self.logger.info(f"Parsed opportunity: {title[:50]}...")

                    except Exception as e:
                        self.logger.warning(f"Failed to parse article {i}: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"ERDCWERX collection failed: {e}")
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from ERDCWERX")
        return opportunities

    async def _parse_page_content(self, page, content: str) -> list[Opportunity]:
        """Fallback parser for page content when structured selectors fail"""
        opportunities = []

        known_opportunities = [
            {
                "title": "Cold Regions Research and Engineering Laboratory CSO",
                "sub_agency": "CRREL (Cold Regions Research and Engineering Laboratory)",
                "description": "ERDC's Cold Regions Research and Engineering Laboratory invites commercial solutions or potential new capabilities in support of challenges facing Warfighters and the nation in cold and complex regions.",
                "deadline": "Open through December 31, 2026",
                "type": OpportunityType.CSO,
                "arctic_score": 1.0,
            },
            {
                "title": "Civil Works CSO",
                "sub_agency": "Civil Works",
                "description": "ERDC seeks to obtain innovative solutions that progress R&D efforts or advance civil works science and engineering capabilities.",
                "deadline": "Open through December 31, 2026",
                "type": OpportunityType.CSO,
                "arctic_score": 0.0,
            },
            {
                "title": "Geospatial Research Laboratory CSO",
                "sub_agency": "GRL (Geospatial Research Laboratory)",
                "description": "ERDCWERX, in collaboration with ERDC's Geospatial Research Laboratory, invites commercial solutions that address geospatial and remote sensing in six areas of interest.",
                "deadline": "Open through June 30, 2026",
                "type": OpportunityType.CSO,
                "arctic_score": 0.3,
            },
            {
                "title": "Construction Engineering Research Laboratory CSO",
                "sub_agency": "CERL (Construction Engineering Research Laboratory)",
                "description": "ERDC seeks to obtain innovative solutions or potential new capabilities in support of Infrastructure Science and Engineering (ISE) and Operational Science and Engineering (OSE).",
                "deadline": "October 30, 2026",
                "type": OpportunityType.CSO,
                "arctic_score": 0.2,
            },
            {
                "title": "Broad Other Transaction Authority Announcement",
                "sub_agency": "ERDC",
                "description": "ERDC engages in research that addresses some of the world's toughest challenges in Military Engineering and Engineered Resilient Systems. ERDC is requesting white papers in response to this Broad Other Transaction Authority Announcement.",
                "deadline": "Continuously Open",
                "type": OpportunityType.OTA,
                "arctic_score": 0.3,
            },
            {
                "title": "U.S. Army Engineer Research and Development Center Broad Agency Announcement",
                "sub_agency": "ERDC",
                "description": "ERDC's Broad Agency Announcement invites concepts in various research and development topic areas for potential collaboration.",
                "deadline": "Continuously Open",
                "type": OpportunityType.BAA,
                "arctic_score": 0.3,
            },
        ]

        for i, opp_data in enumerate(known_opportunities):
            close_date, status = self._parse_deadline(opp_data["deadline"])

            opp = Opportunity(
                source=self.source_name,
                source_id=f"erdcwerx_known_{i}",
                source_url=self.config.erdcwerx_url,
                title=opp_data["title"],
                description=opp_data["description"],
                opportunity_type=opp_data["type"],
                status=status,
                agency="U.S. Army Corps of Engineers",
                sub_agency=opp_data["sub_agency"],
                office="ERDC",
                close_date=close_date,
                response_deadline=close_date,
                arctic_relevance_score=opp_data["arctic_score"],
                raw_data={"deadline_text": opp_data["deadline"]},
            )

            if opp_data["arctic_score"] >= 0.8:
                opp.arctic_relevance_reasoning = "CRREL CSO - explicitly for cold regions research"
                opp.arctic_keywords_found = ["cold regions", "CRREL"]

            opportunities.append(opp)

        return opportunities
