"""Base collector class for all opportunity sources"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ..models import Opportunity

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Abstract base class for all collectors"""

    source_name: str = "unknown"
    source_url: str = ""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.source_name}")
        self.collected_count = 0
        self.error_count = 0
        self.last_run: Optional[datetime] = None

    @abstractmethod
    async def collect(self) -> list[Opportunity]:
        """
        Collect opportunities from the source.
        
        Returns:
            List of Opportunity objects
        """
        pass

    async def run(self) -> dict:
        """
        Run the collector and return statistics.
        
        Returns:
            Dictionary with collection statistics
        """
        self.logger.info(f"Starting collection from {self.source_name}")
        start_time = datetime.utcnow()

        try:
            opportunities = await self.collect()
            self.collected_count = len(opportunities)
            self.last_run = datetime.utcnow()

            self.logger.info(
                f"Collected {self.collected_count} opportunities from {self.source_name}"
            )

            return {
                "source": self.source_name,
                "status": "success",
                "count": self.collected_count,
                "errors": self.error_count,
                "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "opportunities": opportunities,
            }

        except Exception as e:
            self.logger.error(f"Collection failed for {self.source_name}: {e}")
            self.error_count += 1

            return {
                "source": self.source_name,
                "status": "error",
                "count": 0,
                "errors": self.error_count,
                "error_message": str(e),
                "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "opportunities": [],
            }

    def _normalize_date(self, date_str: Optional[str], formats: list[str] = None) -> Optional[datetime]:
        """Parse date string into datetime object"""
        if not date_str:
            return None

        date_str = date_str.strip()

        try:
            from dateutil import parser as dateutil_parser
            return dateutil_parser.parse(date_str, ignoretz=True)
        except Exception:
            pass

        if formats is None:
            formats = [
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y",
                "%m-%d-%Y",
                "%B %d, %Y",
                "%b %d, %Y",
                "%d %B %Y",
                "%d %b %Y",
            ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, AttributeError):
                continue

        return None
