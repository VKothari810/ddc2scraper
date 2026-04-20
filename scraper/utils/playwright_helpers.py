"""Shared Playwright utilities for web scraping"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@asynccontextmanager
async def get_browser_context(
    headless: bool = True,
    user_agent: str = DEFAULT_USER_AGENT,
    viewport: dict = None,
):
    """
    Context manager for Playwright browser and context.
    
    Usage:
        async with get_browser_context() as (browser, context, page):
            await page.goto(url)
            # ... scrape
    """
    if viewport is None:
        viewport = {"width": 1280, "height": 720}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()

        try:
            yield browser, context, page
        finally:
            await browser.close()


async def safe_goto(
    page: Page,
    url: str,
    timeout: int = 60000,
    wait_until: str = "networkidle",
) -> bool:
    """
    Navigate to URL with error handling.
    
    Returns:
        True if navigation successful, False otherwise
    """
    try:
        await page.goto(url, timeout=timeout, wait_until=wait_until)
        return True
    except Exception as e:
        logger.error(f"Failed to navigate to {url}: {e}")
        return False


async def wait_for_content(
    page: Page,
    selector: str,
    timeout: int = 30000,
) -> bool:
    """
    Wait for content to appear on page.
    
    Returns:
        True if element found, False if timeout
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception as e:
        logger.warning(f"Timeout waiting for selector {selector}: {e}")
        return False


async def screenshot_on_error(
    page: Page,
    source_name: str,
    debug_dir: str = "data/debug",
) -> Optional[str]:
    """
    Take a screenshot for debugging purposes.
    
    Returns:
        Path to screenshot file, or None if failed
    """
    try:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        screenshot_path = f"{debug_dir}/{source_name}_error.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"Saved error screenshot to {screenshot_path}")
        return screenshot_path
    except Exception as e:
        logger.error(f"Failed to save screenshot: {e}")
        return None


async def extract_text_content(page: Page, selector: str) -> str:
    """Extract text content from element, returning empty string if not found"""
    try:
        element = await page.query_selector(selector)
        if element:
            return (await element.text_content() or "").strip()
    except Exception:
        pass
    return ""


async def extract_attribute(page: Page, selector: str, attribute: str) -> str:
    """Extract attribute from element, returning empty string if not found"""
    try:
        element = await page.query_selector(selector)
        if element:
            return (await element.get_attribute(attribute) or "").strip()
    except Exception:
        pass
    return ""


async def extract_all_text(page: Page, selector: str) -> list[str]:
    """Extract text content from all matching elements"""
    try:
        elements = await page.query_selector_all(selector)
        texts = []
        for el in elements:
            text = await el.text_content()
            if text:
                texts.append(text.strip())
        return texts
    except Exception:
        return []
