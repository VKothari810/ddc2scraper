"""Shared HTTP client with rate limiting and retries"""
import asyncio
import logging
from typing import Any, Optional

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, rate: float = 1.0):
        """
        Args:
            rate: Maximum requests per second
        """
        self.rate = rate
        self.last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until we can make the next request"""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait_time = max(0, (1.0 / self.rate) - (now - self.last_request))
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_request = asyncio.get_event_loop().time()


class HttpClient:
    """Async HTTP client with rate limiting and retries"""

    def __init__(self, rate_limit: float = 1.0, timeout: int = 30):
        self.rate_limiter = RateLimiter(rate_limit)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=self.timeout, headers=DEFAULT_HEADERS
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def get(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict | str:
        """
        Make a GET request with rate limiting and retries.
        
        Returns:
            JSON dict if response is JSON, otherwise raw text
        """
        await self.rate_limiter.acquire()

        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

        logger.debug(f"GET {url}")
        async with self._session.get(url, params=params, headers=merged_headers) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")

            if "application/json" in content_type:
                return await response.json()
            try:
                return await response.text()
            except UnicodeDecodeError:
                raw = await response.read()
                return raw.decode('utf-8', errors='ignore')

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def post(
        self,
        url: str,
        json_data: Optional[dict] = None,
        data: Optional[Any] = None,
        headers: Optional[dict] = None,
    ) -> dict | str:
        """
        Make a POST request with rate limiting and retries.
        
        Returns:
            JSON dict if response is JSON, otherwise raw text
        """
        await self.rate_limiter.acquire()

        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
        if json_data:
            merged_headers["Content-Type"] = "application/json"

        logger.debug(f"POST {url}")
        async with self._session.post(
            url, json=json_data, data=data, headers=merged_headers
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")

            if "application/json" in content_type:
                return await response.json()
            return await response.text()
