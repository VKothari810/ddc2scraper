"""Navy SBIR collector - parses individual topics from navysbir.com"""
import logging
import re
from typing import Optional
from datetime import datetime

from ..config import get_config
from ..models import Opportunity, OpportunityType, OpportunityStatus
from ..utils.http_client import HttpClient
from .base import BaseCollector

logger = logging.getLogger(__name__)


class NavySbirCollector(BaseCollector):
    """
    Collector for Navy SBIR/STTR individual topics.
    
    Parses the topic listing pages to extract each individual topic
    with its specific link and details.
    """

    source_name = "navy_sbir"
    source_url = "https://www.navysbir.com"

    TOPIC_PAGES = [
        ("https://www.navysbir.com/topics26_1.htm", "DON26BZ01", "SBIR"),
        ("https://www.navysbir.com/topics26_1s.htm", "DON26BZ01", "STTR"),
    ]

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _determine_type(self, text: str) -> OpportunityType:
        """Determine opportunity type from text"""
        text_lower = text.lower() if text else ""
        if "sttr" in text_lower:
            return OpportunityType.STTR
        elif "sbir" in text_lower:
            return OpportunityType.SBIR
        return OpportunityType.SBIR

    def _extract_office(self, topic_id: str, text: str) -> str:
        """Extract the Navy office from topic ID or context"""
        text_upper = (topic_id + " " + text).upper()
        
        offices = {
            "MCSC": "Marine Corps Systems Command",
            "NAVAIR": "Naval Air Systems Command",
            "NAVSEA": "Naval Sea Systems Command", 
            "ONR": "Office of Naval Research",
            "SSP": "Strategic Systems Programs",
            "NAVWAR": "Naval Information Warfare Systems Command",
            "SPAWAR": "Naval Information Warfare Systems Command",
        }
        
        for abbr, name in offices.items():
            if abbr in text_upper:
                return name
        
        return "Navy SBIR Program Office"

    async def _parse_topic_page(self, url: str, baa_number: str, default_type: str) -> list[Opportunity]:
        """Parse a single topic listing page"""
        opportunities = []
        
        try:
            from bs4 import BeautifulSoup
            
            async with HttpClient(rate_limit=1.0, timeout=30) as client:
                self.logger.info(f"Fetching topic page: {url}")
                
                response = await client.get(url)
                if not isinstance(response, str):
                    return []
                
                soup = BeautifulSoup(response, 'lxml')
                
                # Find all topic links - they follow pattern like DON26BZ01-NV001
                topic_links = soup.find_all('a', href=re.compile(r'DON\d+[A-Z]+\d*-[A-Z]+\d+\.htm', re.IGNORECASE))
                
                current_office = ""
                
                # Also scan text for office headers
                for element in soup.find_all(['td', 'tr', 'p', 'div']):
                    text = element.get_text(strip=True)
                    
                    # Check for office headers like "NAVAIR - DON26BZ01 SBIR Conventional Topics:"
                    office_match = re.match(r'^(MCSC|NAVAIR|NAVSEA|ONR|SSP|NAVWAR|SPAWAR)\s*[-–]', text)
                    if office_match:
                        current_office = office_match.group(1)
                
                for link in topic_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    if not title or len(title) < 5:
                        continue
                    
                    # Extract topic number from title or href
                    # Format: "NV001 - Amphibious Combat Vehicle..."
                    topic_match = re.search(r'([A-Z]{2}\d{3})\s*[-–]\s*(.+)', title)
                    if topic_match:
                        topic_number = topic_match.group(1)
                        topic_title = topic_match.group(2).strip()
                    else:
                        # Try to extract from href
                        href_match = re.search(r'-([A-Z]{2}\d{3})\.htm', href, re.IGNORECASE)
                        topic_number = href_match.group(1).upper() if href_match else ""
                        topic_title = title
                    
                    # Build full URL
                    if href and not href.startswith('http'):
                        full_url = f"{self.source_url}/{href}" if not href.startswith('/') else f"{self.source_url}{href}"
                    else:
                        full_url = href or url
                    
                    # Determine if Direct to Phase II
                    is_d2p2 = topic_number.startswith('DV') or 'direct to phase' in title.lower()
                    
                    # Determine opportunity type
                    if 'sttr' in default_type.lower() or 'sttr' in title.lower():
                        opp_type = OpportunityType.STTR
                    else:
                        opp_type = OpportunityType.SBIR
                    
                    # Extract office from context
                    office = self._extract_office(topic_number, title)
                    
                    # Create solicitation number
                    sol_number = f"{baa_number}-{topic_number}" if topic_number else baa_number
                    
                    opp = Opportunity(
                        source=self.source_name,
                        source_id=f"navy_sbir_{sol_number}",
                        source_url=full_url,
                        solicitation_number=sol_number,
                        title=f"{topic_number} - {topic_title}" if topic_number else topic_title,
                        description=f"Navy {'Direct to Phase II ' if is_d2p2 else ''}{opp_type.value} Topic: {topic_title}",
                        opportunity_type=opp_type,
                        status=OpportunityStatus.OPEN,
                        agency="Department of Defense",
                        sub_agency="U.S. Navy",
                        office=office,
                        raw_data={
                            "baa_number": baa_number,
                            "topic_number": topic_number,
                            "is_direct_to_phase_2": is_d2p2,
                            "scraped_from": url,
                        },
                    )
                    opportunities.append(opp)
                    self.logger.info(f"Found topic: {sol_number} - {topic_title[:40]}...")
                
        except Exception as e:
            self.logger.error(f"Failed to parse {url}: {e}")
        
        return opportunities

    async def collect(self) -> list[Opportunity]:
        """Collect individual Navy SBIR/STTR topics"""
        all_opportunities = []

        for url, baa_number, default_type in self.TOPIC_PAGES:
            try:
                opps = await self._parse_topic_page(url, baa_number, default_type)
                all_opportunities.extend(opps)
            except Exception as e:
                self.logger.error(f"Failed to collect from {url}: {e}")

        # Deduplicate by source_id
        seen = set()
        unique = []
        for opp in all_opportunities:
            if opp.source_id not in seen:
                seen.add(opp.source_id)
                unique.append(opp)

        self.logger.info(f"Collected {len(unique)} individual Navy SBIR/STTR topics")
        return unique
