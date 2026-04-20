"""DIU (Defense Innovation Unit) collector"""
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


class DiuCollector(BaseCollector):
    """
    Collector for Defense Innovation Unit (DIU) open solicitations.
    
    DIU posts Commercial Solutions Openings (CSOs) using Other Transaction Authority.
    """

    source_name = "diu"
    source_url = "https://www.diu.mil"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _parse_portfolio(self, text: str) -> str:
        """Determine DIU portfolio area from text"""
        text_lower = text.lower() if text else ""

        portfolios = {
            "ai": "Artificial Intelligence",
            "ml": "Machine Learning",
            "autonomy": "Autonomy",
            "cyber": "Cyber",
            "energy": "Energy",
            "human systems": "Human Systems",
            "space": "Space",
            "advanced materials": "Advanced Materials",
        }

        for key, name in portfolios.items():
            if key in text_lower:
                return name

        return "General"

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from DIU"""
        opportunities = []

        try:
            async with get_browser_context() as (browser, context, page):
                url = f"{self.config.diu_url}"
                self.logger.info(f"Navigating to {url}")

                if not await safe_goto(page, url, timeout=60000):
                    await screenshot_on_error(page, self.source_name, self.config.debug_dir)
                    return []

                await page.wait_for_timeout(3000)

                sol_link = await page.query_selector(
                    "a[href*='open-solicitations'], a[href*='solicitation'], a:has-text('Open Solicitations')"
                )
                if sol_link:
                    href = await sol_link.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"{self.source_url}{href}"
                        self.logger.info(f"Navigating to solicitations page: {href}")
                        await safe_goto(page, href, timeout=60000)
                        await page.wait_for_timeout(3000)

                card_selectors = [
                    ".solicitation-card",
                    ".opportunity-card",
                    ".card",
                    "article",
                    ".post",
                    ".solicitation",
                    "[data-solicitation]",
                ]

                cards = []
                for selector in card_selectors:
                    cards = await page.query_selector_all(selector)
                    if cards:
                        self.logger.info(f"Found {len(cards)} cards using: {selector}")
                        break

                if not cards:
                    self.logger.info("No structured cards found, trying content extraction")
                    opportunities = await self._extract_from_content(page)
                    return opportunities

                for i, card in enumerate(cards):
                    try:
                        title_el = await card.query_selector(
                            "h2, h3, h4, .title, .card-title, a"
                        )
                        if not title_el:
                            continue

                        title = (await title_el.text_content() or "").strip()
                        if not title or len(title) < 5:
                            continue

                        if any(skip in title.lower() for skip in ["menu", "navigation", "footer", "header"]):
                            continue

                        link_el = await card.query_selector("a[href]")
                        link = ""
                        if link_el:
                            link = await link_el.get_attribute("href") or ""
                            if link and not link.startswith("http"):
                                link = f"{self.source_url}{link}"

                        desc_el = await card.query_selector("p, .description, .summary, .excerpt")
                        description = ""
                        if desc_el:
                            description = (await desc_el.text_content() or "").strip()

                        date_el = await card.query_selector(
                            ".date, .deadline, time, [data-date]"
                        )
                        close_date = None
                        if date_el:
                            date_text = await date_el.text_content()
                            close_date = self._normalize_date(date_text)

                        card_text = await card.text_content() or ""
                        date_match = re.search(
                            r"(?:due|deadline|closes?|submit by)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
                            card_text,
                            re.IGNORECASE
                        )
                        if date_match and not close_date:
                            close_date = self._normalize_date(date_match.group(1))

                        status = OpportunityStatus.OPEN
                        if close_date and close_date < datetime.now():
                            status = OpportunityStatus.CLOSED

                        portfolio = self._parse_portfolio(title + " " + description)

                        opp = Opportunity(
                            source=self.source_name,
                            source_id=f"diu_{i}_{hash(title) % 10000}",
                            source_url=link or url,
                            title=title,
                            description=description,
                            opportunity_type=OpportunityType.CSO,
                            status=status,
                            agency="Department of Defense",
                            sub_agency="Defense Innovation Unit",
                            office=portfolio,
                            close_date=close_date,
                            response_deadline=close_date,
                            raw_data={
                                "portfolio": portfolio,
                                "scraped_from": url,
                            },
                        )

                        opportunities.append(opp)
                        self.logger.info(f"Parsed: {title[:50]}...")

                    except Exception as e:
                        self.logger.warning(f"Failed to parse card {i}: {e}")

        except Exception as e:
            self.logger.error(f"DIU collection failed: {e}")
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from DIU")
        return opportunities

    async def _extract_from_content(self, page) -> list[Opportunity]:
        """Extract opportunities from page content"""
        opportunities = []

        try:
            all_links = await page.query_selector_all("a[href]")

            for link_el in all_links:
                try:
                    href = await link_el.get_attribute("href") or ""
                    text = (await link_el.text_content() or "").strip()

                    if not text or len(text) < 10:
                        continue

                    keywords = ["solicitation", "cso", "opportunity", "rfp", "rfi"]
                    if not any(kw in href.lower() or kw in text.lower() for kw in keywords):
                        continue

                    if any(skip in text.lower() for skip in ["submit", "login", "contact", "about"]):
                        continue

                    if not href.startswith("http"):
                        href = f"{self.source_url}{href}"

                    opp = Opportunity(
                        source=self.source_name,
                        source_id=f"diu_{hash(text) % 100000}",
                        source_url=href,
                        title=text,
                        description="",
                        opportunity_type=OpportunityType.CSO,
                        status=OpportunityStatus.OPEN,
                        agency="Department of Defense",
                        sub_agency="Defense Innovation Unit",
                        raw_data={"extracted_from_links": True},
                    )
                    opportunities.append(opp)

                except Exception:
                    continue

        except Exception as e:
            self.logger.warning(f"Content extraction failed: {e}")

        return opportunities
