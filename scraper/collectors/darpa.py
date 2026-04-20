"""DARPA opportunities collector - scrapes from DARPA website and SAM.gov"""
import logging
import re
from datetime import datetime
from typing import Any, Optional
import xml.etree.ElementTree as ET

from playwright.async_api import Page

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

# Opportunity tiles on https://www.darpa.mil/work-with-us/opportunities (React / Tailwind)
_CARD_HOST_SELECTOR = ".opportunities-section-wrapper"
# Tailwind arbitrary width class on each tile; brackets must not be used inside querySelector.
_CARD_FILTER_SUBSTR = "w-[337px]"

_SAM_OPP_RE = re.compile(
    r"https?://sam\.gov/(?:opp/([a-f0-9-]+)/view|workspace/contract/opp/([a-f0-9-]+)/view)",
    re.I,
)


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

    @staticmethod
    def _looks_like_solicitation_id(line: str) -> bool:
        """Heuristic: first line of a tile is often HR…, DARPA-…, DARPARA…, etc."""
        s = (line or "").strip()
        if not s or len(s) > 96:
            return False
        if s.lower().startswith("deadline"):
            return False
        # Titles are usually longer prose with several words
        if len(s.split()) > 6 and not re.match(r"^[A-Z0-9][A-Z0-9\-./]+$", s):
            return False
        return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9\-./]{2,}$", s))

    async def _expand_darpa_opportunity_tiles(self, page: Page, max_clicks: int = 80) -> int:
        """Click through every 'Show More' so all React-rendered opportunity cards load."""
        clicks = 0
        while clicks < max_clicks:
            btn = page.get_by_role("button", name=re.compile(r"show\s+more", re.I))
            if await btn.count() == 0:
                break
            try:
                await btn.first.click(timeout=15000)
                clicks += 1
                await page.wait_for_timeout(600)
            except Exception as e:
                self.logger.debug(f"Show More click stopped: {e}")
                break
        if clicks:
            self.logger.info(f"DARPA opportunities page: expanded tiles with {clicks} 'Show More' click(s)")
        return clicks

    async def _extract_darpa_opportunity_cards(self, page: Page) -> list[dict[str, Any]]:
        """Return structured card payloads from the opportunities grid (same-origin evaluate)."""
        host = _CARD_HOST_SELECTOR
        filt = _CARD_FILTER_SUBSTR
        return await page.evaluate(
            """({ host, filt }) => {
              const root = document.querySelector(host) || document.body;
              const nodes = Array.from(root.querySelectorAll('div.flex.relative'));
              const cards = nodes.filter((d) => (d.className || '').includes(filt));
              return cards.map((card) => {
                const lines = (card.innerText || '')
                  .trim()
                  .split(/\\n+/)
                  .map((s) => s.trim())
                  .filter(Boolean);
                const links = Array.from(card.querySelectorAll('a[href]')).map((a) => ({
                  href: a.href,
                  text: (a.innerText || '').trim(),
                }));
                return { lines, links };
              });
            }""",
            {"host": host, "filt": filt},
        )

    @staticmethod
    def _is_generic_dsip_active_listing(url: str) -> bool:
        """Many SBIR tiles reuse the same DSIP 'active solicitations' hub URL — avoid as primary."""
        u = (url or "").lower()
        return "dodsbirsttr.mil" in u and "active-solicitations" in u

    def _pick_primary_url(self, links: list[dict[str, str]]) -> str:
        """
        Prefer canonical SAM URLs, then DARPA program/challenge pages and PDFs.

        Generic DSIP 'active solicitations' listings are ranked last so each tile keeps
        a distinct `darpa.mil/research/...` (or PDF) URL when present.
        """
        if not links:
            return self.source_url

        def hrefs():
            for L in links:
                h = (L.get("href") or "").strip()
                if h:
                    yield h

        ranked: list[tuple[int, str]] = []
        for h in hrefs():
            hlow = h.lower()
            if "sam.gov/opp/" in hlow and "/view" in hlow:
                ranked.append((0, h))
            elif "sam.gov/workspace/contract/opp/" in hlow and "/view" in hlow:
                ranked.append((1, h))
            elif "sam.gov" in hlow and "opp" in hlow:
                ranked.append((2, h))
            elif hlow.endswith(".pdf") and "darpa.mil" in hlow:
                ranked.append((3, h))
            elif "darpa.mil/research/" in hlow:
                ranked.append((4, h))
            elif "darpa.mil/events/" in hlow:
                ranked.append((5, h))
            elif "darpaconnect.us" in hlow:
                ranked.append((6, h))
            elif "dodsbirsttr.mil" in hlow:
                pr = 50 if self._is_generic_dsip_active_listing(h) else 7
                ranked.append((pr, h))
            elif "darpa.mil/about/offices/" in hlow:
                ranked.append((20, h))

        if ranked:
            ranked.sort(key=lambda x: x[0])
            return ranked[0][1]

        return links[0]["href"]

    def _sam_uuid_from_url(self, url: str) -> Optional[str]:
        m = _SAM_OPP_RE.search(url or "")
        if not m:
            return None
        return (m.group(1) or m.group(2) or "").lower() or None

    def _title_from_card(self, lines: list[str], links: list[dict[str, str]]) -> str:
        for L in links:
            t = (L.get("text") or "").strip()
            h = (L.get("href") or "").lower()
            if not t or len(t) < 3:
                continue
            tl = t.lower()
            if tl.startswith("see ") and len(t) < 24:
                continue
            if tl in ("amendment 1", "amendment 2", "amendment"):
                continue
            if "sam.gov" in h and "/opp/" in h:
                return t
            if "sam.gov/workspace" in h and "opp" in h:
                return t
        if lines:
            idx = 1 if len(lines) > 1 and self._looks_like_solicitation_id(lines[0]) else 0
            if idx < len(lines) and not lines[idx].lower().startswith("deadline date:"):
                return lines[idx]
        for L in links:
            t = (L.get("text") or "").strip()
            if t and not t.lower().startswith("see "):
                return t
        return "DARPA opportunity"

    def _parse_card_lines(
        self, lines: list[str]
    ) -> tuple[Optional[str], str, str, Optional[datetime], str]:
        """
        Returns: solicitation_number, title_fallback, description, deadline, office_line
        title_fallback is used only if link text is useless; usually overridden by _title_from_card.
        """
        lines = [ln.strip() for ln in lines if ln.strip()]
        deadline_dt: Optional[datetime] = None
        deadline_idx: Optional[int] = None
        for i, ln in enumerate(lines):
            if ln.lower().startswith("deadline date:"):
                deadline_idx = i
                deadline_dt = self._normalize_date(ln.split(":", 1)[1].strip())
                break

        body_end = deadline_idx if deadline_idx is not None else len(lines)
        office = ""
        if deadline_idx is not None and deadline_idx + 1 < len(lines):
            office = lines[deadline_idx + 1].strip()

        has_sol = bool(lines) and self._looks_like_solicitation_id(lines[0])
        sol = lines[0].strip() if has_sol else None

        if has_sol:
            title_fb = lines[1] if body_end > 1 else ""
            desc_parts = lines[2:body_end] if body_end > 2 else []
        else:
            title_fb = lines[0] if lines else ""
            desc_parts = lines[1:body_end] if body_end > 1 else []

        description = "\n\n".join(desc_parts).strip()
        description = re.sub(r"\s*\|\s*See\s+[^|]+\s*$", "", description).strip()

        return sol, title_fb, description, deadline_dt, office

    def _opportunity_from_card_payload(self, payload: dict[str, Any]) -> Optional[Opportunity]:
        lines = payload.get("lines") or []
        links = payload.get("links") or []
        if not lines and not links:
            return None

        primary_url = self._pick_primary_url(links)
        sam_uuid = self._sam_uuid_from_url(primary_url)

        sol, title_fb, description, deadline_dt, office_line = self._parse_card_lines(lines)
        title = self._title_from_card(lines, links)
        if not title or title.lower() in ("see program", "see topic", "see challenge", "see office"):
            title = title_fb or title

        office = office_line or self._determine_office(" ".join(lines))

        if sam_uuid:
            source_id = f"darpa_site_{sam_uuid}"
        elif sol:
            source_id = f"darpa_site_{re.sub(r'[^a-zA-Z0-9]+', '_', sol).strip('_').lower()}"
        else:
            source_id = f"darpa_site_{abs(hash(primary_url + title)) % 10_000_000}"

        raw = {
            "source": "darpa_opportunities_page",
            "card_lines": lines,
            "card_links": links,
            "primary_url": primary_url,
        }

        return Opportunity(
            source=self.source_name,
            source_id=source_id,
            source_url=primary_url,
            title=title.strip()[:500],
            description=(description or "")[:4000],
            opportunity_type=self._determine_type(f"{title} {description}"),
            status=OpportunityStatus.OPEN,
            solicitation_number=sol,
            agency="Department of Defense",
            sub_agency="DARPA",
            office=office[:200] if office else self._determine_office(title),
            posted_date=None,
            close_date=deadline_dt,
            response_deadline=deadline_dt,
            raw_data=raw,
        )

    async def _scrape_darpa_website(self) -> list[Opportunity]:
        """
        Scrape https://www.darpa.mil/work-with-us/opportunities.

        Loads every tile by clicking through all “Show More” controls, then parses each
        white card (solicitation id, title, blurb, deadline, office, SAM / PDF / program URLs).
        """
        opportunities: list[Opportunity] = []

        try:
            async with get_browser_context(
                viewport={"width": 1440, "height": 1200},
            ) as (_browser, _context, page):
                url = "https://www.darpa.mil/work-with-us/opportunities"
                self.logger.info(f"Navigating to {url}")

                if not await safe_goto(page, url, timeout=90000):
                    await screenshot_on_error(page, self.source_name)
                    return []

                await page.wait_for_timeout(2500)
                try:
                    await page.wait_for_selector(_CARD_HOST_SELECTOR, timeout=20000)
                except Exception:
                    self.logger.warning("DARPA opportunities host selector not found; continuing")

                await self._expand_darpa_opportunity_tiles(page)

                cards = await self._extract_darpa_opportunity_cards(page)
                self.logger.info(f"DARPA website: parsed {len(cards)} opportunity card(s) after expansion")

                seen_url: set[str] = set()
                for payload in cards:
                    try:
                        opp = self._opportunity_from_card_payload(payload)
                        if not opp:
                            continue
                        key = opp.source_url.split("?", 1)[0].rstrip("/").lower()
                        if key in seen_url:
                            continue
                        seen_url.add(key)
                        opportunities.append(opp)
                    except Exception as e:
                        self.logger.warning(f"DARPA card parse failed: {e}")
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

        # Deduplicate by SAM notice UUID (classic + workspace URLs) or stable title prefix
        seen = set()
        unique = []
        for opp in all_opportunities:
            key = opp.title.lower().strip()[:48]
            sam_uuid = self._sam_uuid_from_url(opp.source_url)
            if sam_uuid:
                key = sam_uuid
            elif opp.solicitation_number:
                key = opp.solicitation_number.strip().lower()

            if key not in seen:
                seen.add(key)
                unique.append(opp)

        self.logger.info(f"Collected {len(unique)} unique DARPA opportunities")
        return unique
