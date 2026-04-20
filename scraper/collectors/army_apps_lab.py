"""Army Applications Lab (AAL) collector"""
import logging
import re
from typing import Optional
from datetime import datetime

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class ArmyAppsLabCollector(BaseCollector):
    """
    Collector for Army Applications Lab (AAL) opportunities.
    
    AAL is part of Army Futures Command and focuses on rapid prototyping
    and CSOs for emerging technologies.
    """

    source_name = "army_apps_lab"
    source_url = "https://www.aal.army"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _determine_type(self, title: str) -> OpportunityType:
        """Determine opportunity type"""
        title_lower = title.lower() if title else ""

        if "cso" in title_lower or "commercial solutions" in title_lower:
            return OpportunityType.CSO
        elif "ota" in title_lower or "other transaction" in title_lower:
            return OpportunityType.OTA
        elif "sbir" in title_lower:
            return OpportunityType.SBIR
        elif "call for solution" in title_lower or "cfs" in title_lower:
            return OpportunityType.CSO

        return OpportunityType.CSO

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from Army Applications Lab"""
        opportunities = []

        try:
            from bs4 import BeautifulSoup
            
            async with HttpClient(rate_limit=1.0, timeout=30) as client:
                urls_to_try = [
                    f"{self.config.army_apps_lab_url}",
                    "https://aal.army/industry/",
                ]
                
                for url in urls_to_try:
                    try:
                        self.logger.info(f"Fetching {url}")
                        html = await client.get(url)
                        
                        if not isinstance(html, str):
                            continue
                            
                        soup = BeautifulSoup(html, 'lxml')
                        
                        for link in soup.find_all('a', href=True):
                            href = link.get('href', '')
                            text = link.get_text(strip=True)
                            
                            if not text or len(text) < 10:
                                continue
                            
                            keywords = ['call for solution', 'cfs', 'aal', 'opportunity', 'open call', 'challenge']
                            is_opportunity = any(kw in text.lower() or kw in href.lower() for kw in keywords)
                            
                            if is_opportunity:
                                skip_words = ['join', 'network', 'advantage', 'about', 'contact', 'login', 'faq', 
                                             'follow', 'linkedin', 'youtube', 'media', 'inquir', 'twitter', 'facebook',
                                             'no fear', 'nofear', 'privacy', 'accessibility']
                                if any(skip in text.lower() for skip in skip_words):
                                    continue
                                
                                if not href.startswith('http'):
                                    href = f"https://aal.army{href}" if href.startswith('/') else f"https://aal.army/{href}"
                                
                                opp = Opportunity(
                                    source=self.source_name,
                                    source_id=f"aal_{hash(text) % 100000}",
                                    source_url=href,
                                    title=text,
                                    description="",
                                    opportunity_type=self._determine_type(text),
                                    status=OpportunityStatus.OPEN,
                                    agency="Department of Defense",
                                    sub_agency="U.S. Army",
                                    office="Army Applications Lab",
                                    raw_data={"scraped_from": url},
                                )
                                opportunities.append(opp)
                                self.logger.info(f"Found: {text[:50]}...")
                        
                        for el in soup.find_all(['div', 'section', 'article'], class_=re.compile(r'opportunity|cfs|call|challenge')):
                            title_el = el.find(['h2', 'h3', 'h4', 'a', 'strong'])
                            if title_el:
                                title = title_el.get_text(strip=True)
                                if len(title) > 15:
                                    link_el = el.find('a', href=True)
                                    link = link_el.get('href', url) if link_el else url
                                    
                                    if not link.startswith('http'):
                                        link = f"https://aal.army{link}"
                                    
                                    opp_id = f"aal_div_{hash(title) % 100000}"
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
                                            sub_agency="U.S. Army",
                                            office="Army Applications Lab",
                                            raw_data={"scraped_from": url},
                                        )
                                        opportunities.append(opp)
                                        
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch {url}: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"AAL collection failed: {e}")
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from AAL")
        return opportunities
