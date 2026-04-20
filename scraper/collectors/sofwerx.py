"""SOFWERX (SOCOM innovation hub) collector"""
import logging
import re
from typing import Optional
from datetime import datetime

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class SofwerxCollector(BaseCollector):
    """
    Collector for SOFWERX challenges and opportunities.
    
    SOFWERX serves as an innovation platform for U.S. Special Operations Command.
    Uses HTTP client instead of Playwright due to site timeout issues.
    """

    source_name = "sofwerx"
    source_url = "https://sofwerx.org"
    events_url = "https://events.sofwerx.org"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _determine_type(self, title: str) -> OpportunityType:
        """Determine opportunity type from title"""
        title_lower = title.lower() if title else ""

        if "sbir" in title_lower:
            return OpportunityType.SBIR
        elif "sttr" in title_lower:
            return OpportunityType.STTR
        elif "rca" in title_lower or "rapid capability" in title_lower:
            return OpportunityType.OTHER
        elif "prize" in title_lower or "challenge" in title_lower:
            return OpportunityType.OTHER

        return OpportunityType.OTHER

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from SOFWERX"""
        opportunities = []

        try:
            from bs4 import BeautifulSoup
            
            async with HttpClient(rate_limit=0.5, timeout=45) as client:
                urls_to_try = [
                    self.events_url,
                    self.source_url,
                ]
                
                for url in urls_to_try:
                    try:
                        self.logger.info(f"Fetching {url}")
                        html = await client.get(url)
                        
                        if not isinstance(html, str):
                            continue
                            
                        soup = BeautifulSoup(html, 'lxml')
                        
                        event_selectors = [
                            soup.find_all('div', class_=re.compile(r'event|challenge|card')),
                            soup.find_all('article'),
                            soup.find_all('a', href=re.compile(r'event|challenge|rca|sbir')),
                        ]
                        
                        for elements in event_selectors:
                            for el in elements:
                                title = ""
                                link = ""
                                
                                if el.name == 'a':
                                    title = el.get_text(strip=True)
                                    link = el.get('href', '')
                                else:
                                    title_el = el.find(['h2', 'h3', 'h4', 'a'])
                                    if title_el:
                                        title = title_el.get_text(strip=True)
                                        if title_el.name == 'a':
                                            link = title_el.get('href', '')
                                    
                                    if not link:
                                        link_el = el.find('a', href=True)
                                        if link_el:
                                            link = link_el.get('href', '')
                                
                                if not title or len(title) < 10:
                                    continue
                                
                                skip_words = ['menu', 'nav', 'footer', 'login', 'sign up', 'contact', 'about', 
                                             'current events', 'past events', 'external events', 'browse', 'view', 
                                             'join upcoming', 'follow us', 'subscribe', 'statistics', 'quantity']
                                if any(skip in title.lower() for skip in skip_words):
                                    continue
                                
                                required_words = ['challenge', 'rca', 'sbir', 'sttr', 'sprint', 'assessment', 
                                                 'competition', 'roundtable', 'hydrogen', 'autonomous', 'production']
                                if not any(req in title.lower() for req in required_words):
                                    continue
                                
                                if link and not link.startswith('http'):
                                    base = url.rstrip('/')
                                    link = f"{base}{link}" if link.startswith('/') else f"{base}/{link}"
                                
                                if not link:
                                    link = url
                                
                                date_text = el.get_text()
                                event_date = None
                                date_match = re.search(
                                    r'(\w+\s+\d{1,2},?\s+\d{4})|(\d{1,2}/\d{1,2}/\d{4})',
                                    date_text
                                )
                                if date_match:
                                    event_date = self._normalize_date(date_match.group(0))
                                
                                opp_id = f"sofwerx_{hash(title) % 100000}"
                                
                                if not any(o.source_id == opp_id for o in opportunities):
                                    opp = Opportunity(
                                        source=self.source_name,
                                        source_id=opp_id,
                                        source_url=link,
                                        title=title,
                                        description="",
                                        opportunity_type=self._determine_type(title),
                                        status=OpportunityStatus.OPEN,
                                        agency="Department of Defense",
                                        sub_agency="U.S. Special Operations Command",
                                        office="SOFWERX",
                                        close_date=event_date,
                                        response_deadline=event_date,
                                        raw_data={"scraped_from": url},
                                    )
                                    opportunities.append(opp)
                                    self.logger.info(f"Found: {title[:50]}...")
                                    
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch {url}: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"SOFWERX collection failed: {e}")
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from SOFWERX")
        return opportunities
