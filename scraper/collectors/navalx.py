"""NavalX Tech Bridges collector"""
import logging
import re
from typing import Optional
from datetime import datetime

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class NavalxCollector(BaseCollector):
    """
    Collector for NavalX Tech Bridges opportunities.
    
    NavalX operates 15 Tech Bridges across the US that connect
    the Navy with startups and small businesses.
    
    Uses Navy Tech Connect as primary source since navalx.nre.navy.mil
    returns 403.
    """

    source_name = "navalx"
    source_url = "https://www.navytechconnect.com"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from NavalX via Navy Tech Connect"""
        opportunities = []

        try:
            from bs4 import BeautifulSoup
            
            async with HttpClient(rate_limit=1.0, timeout=30) as client:
                self.logger.info(f"Fetching {self.source_url}")
                
                try:
                    html = await client.get(self.source_url)
                    
                    if isinstance(html, str):
                        soup = BeautifulSoup(html, 'lxml')
                        
                        links = soup.find_all('a', href=True)
                        
                        for link in links:
                            href = link.get('href', '')
                            text = link.get_text(strip=True)
                            
                            if not text or len(text) < 10:
                                continue
                            
                            keywords = ['challenge', 'opportunity', 'solicitation', 'pitch', 'competition', 'sprint']
                            if any(kw in text.lower() or kw in href.lower() for kw in keywords):
                                if any(skip in text.lower() for skip in ['login', 'submit', 'register', 'contact']):
                                    continue
                                
                                if not href.startswith('http'):
                                    href = f"{self.source_url}{href}" if href.startswith('/') else f"{self.source_url}/{href}"
                                
                                opp_type = OpportunityType.OTHER
                                if 'sbir' in text.lower():
                                    opp_type = OpportunityType.SBIR
                                elif 'sttr' in text.lower():
                                    opp_type = OpportunityType.STTR
                                
                                opp = Opportunity(
                                    source=self.source_name,
                                    source_id=f"navalx_{hash(text) % 100000}",
                                    source_url=href,
                                    title=text,
                                    description="",
                                    opportunity_type=opp_type,
                                    status=OpportunityStatus.OPEN,
                                    agency="Department of Defense",
                                    sub_agency="U.S. Navy",
                                    office="NavalX Tech Bridge",
                                    raw_data={"scraped_from": self.source_url},
                                )
                                opportunities.append(opp)
                                self.logger.info(f"Found: {text[:50]}...")
                        
                except Exception as e:
                    self.logger.warning(f"Failed to fetch Navy Tech Connect: {e}")

                self.logger.info("Trying alternative Navy innovation sources...")
                
                alt_urls = [
                    "https://www.onr.navy.mil/work-with-us/funding-opportunities",
                ]
                
                for url in alt_urls:
                    try:
                        html = await client.get(url)
                        if isinstance(html, str):
                            soup = BeautifulSoup(html, 'lxml')
                            
                            for article in soup.find_all(['article', 'div'], class_=re.compile(r'opportunity|funding|grant')):
                                title_el = article.find(['h2', 'h3', 'h4', 'a'])
                                if title_el:
                                    title = title_el.get_text(strip=True)
                                    if len(title) > 15:
                                        link = title_el.get('href', url) if title_el.name == 'a' else url
                                        if not link.startswith('http'):
                                            link = f"https://www.onr.navy.mil{link}"
                                        
                                        opp = Opportunity(
                                            source=self.source_name,
                                            source_id=f"navalx_onr_{hash(title) % 100000}",
                                            source_url=link,
                                            title=title,
                                            description="",
                                            opportunity_type=OpportunityType.BAA,
                                            status=OpportunityStatus.OPEN,
                                            agency="Department of Defense",
                                            sub_agency="U.S. Navy",
                                            office="Office of Naval Research",
                                            raw_data={"scraped_from": url},
                                        )
                                        opportunities.append(opp)
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch {url}: {e}")

        except Exception as e:
            self.logger.error(f"NavalX collection failed: {e}")
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from NavalX")
        return opportunities
