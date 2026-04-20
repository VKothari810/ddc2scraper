"""SpaceWERX collector"""
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


class SpacewerxCollector(BaseCollector):
    """
    Collector for SpaceWERX (Space Force SBIR/STTR) opportunities.
    
    SpaceWERX manages the U.S. Space Force's SBIR/STTR programs.
    Uses the same page structure as AFWERX.
    """

    source_name = "spacewerx"
    source_url = "https://spacewerx.us"

    def __init__(self):
        super().__init__()
        self.config = get_config()

    def _parse_date(self, text: str) -> Optional[datetime]:
        """Parse date from various formats"""
        if not text or text.strip().upper() == "N/A":
            return None

        text = text.strip()
        
        month_map = {
            'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
            'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
            'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
        }

        match = re.match(r'(\d{1,2})\s+([A-Z]+)\s+(\d{2,4})', text.upper())
        if match:
            day, month_str, year = match.groups()
            month = month_map.get(month_str)
            if month:
                if len(year) == 2:
                    year = '20' + year
                try:
                    return datetime.strptime(f"{year}-{month}-{day.zfill(2)}", "%Y-%m-%d")
                except ValueError:
                    pass

        return self._normalize_date(text)

    def _determine_type(self, title: str) -> OpportunityType:
        """Determine opportunity type from title"""
        title_lower = title.lower() if title else ""

        if "sttr" in title_lower:
            return OpportunityType.STTR
        elif "sbir" in title_lower:
            return OpportunityType.SBIR
        elif "stratfi" in title_lower or "tacfi" in title_lower:
            return OpportunityType.OTHER
        elif "baa" in title_lower:
            return OpportunityType.BAA

        return OpportunityType.SBIR

    async def collect(self) -> list[Opportunity]:
        """Collect opportunities from SpaceWERX"""
        opportunities = []

        try:
            async with get_browser_context() as (browser, context, page):
                self.logger.info(f"Navigating to {self.config.spacewerx_url}")

                if not await safe_goto(page, self.config.spacewerx_url, timeout=60000):
                    await screenshot_on_error(page, self.source_name, self.config.debug_dir)
                    return []

                await page.wait_for_timeout(3000)

                body_text = await page.inner_text("body")
                lines = [l.strip() for l in body_text.split("\n") if l.strip()]
                
                i = 0
                while i < len(lines):
                    line = lines[i]

                    is_solicitation = (
                        ("DOD" in line.upper() or "DAF" in line.upper() or "DOW" in line.upper() or "PY26" in line.upper()) and
                        any(kw in line.upper() for kw in ["SBIR", "STTR", "STRATFI", "TACFI", "RELEASE", "TOPIC", "NOTICE OF OPPORTUNITY"])
                    )
                    
                    if is_solicitation and len(line) > 20 and not line.startswith("SOLICITATION:"):
                        title = line
                        
                        pre_release = None
                        open_date = None
                        close_date = None
                        
                        for j in range(i + 1, min(i + 6, len(lines))):
                            next_line = lines[j]
                            
                            if next_line.startswith("SOLICITATION:") or ("DOD" in next_line.upper() and "SBIR" in next_line.upper()):
                                break
                                
                            parsed = self._parse_date(next_line)
                            if parsed:
                                if pre_release is None:
                                    pre_release = parsed
                                elif open_date is None:
                                    open_date = parsed
                                elif close_date is None:
                                    close_date = parsed
                                    break
                        
                        final_close = close_date or open_date
                        final_open = open_date or pre_release
                        
                        if final_close or final_open:
                            status = OpportunityStatus.UNKNOWN
                            now = datetime.now()
                            if final_close and final_close < now:
                                status = OpportunityStatus.CLOSED
                            elif final_open and final_open <= now:
                                status = OpportunityStatus.OPEN
                            elif final_open and final_open > now:
                                status = OpportunityStatus.FORECASTED
                            
                            opp = Opportunity(
                                source=self.source_name,
                                source_id=f"spacewerx_{hash(title) % 100000}",
                                source_url=self.config.spacewerx_url,
                                title=title,
                                description="",
                                opportunity_type=self._determine_type(title),
                                status=status,
                                agency="Department of Defense",
                                sub_agency="U.S. Space Force",
                                office="SpaceWERX",
                                posted_date=final_open,
                                close_date=final_close,
                                response_deadline=final_close,
                                raw_data={"scraped_from": self.config.spacewerx_url},
                            )

                            opportunities.append(opp)
                            self.logger.info(f"Parsed: {title[:50]}...")
                    
                    i += 1

        except Exception as e:
            self.logger.error(f"SpaceWERX collection failed: {e}")
            import traceback
            traceback.print_exc()
            return []

        self.logger.info(f"Collected {len(opportunities)} opportunities from SpaceWERX")
        return opportunities
