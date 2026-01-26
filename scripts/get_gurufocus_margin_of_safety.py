# -*- coding: utf-8 -*-
"""
GuruFocus Margin of Safety (MOS) extractor.

Primary entrypoint:
  get_margin_of_safety(ticker: str) -> float | None

Strategy:
- Try fast HTML fetch with requests (may 403)
- Fall back to Playwright (browser) which is much more reliable
- Supports negative MOS values (e.g., -19.02%)

Install (local):
  pip install requests beautifulsoup4 playwright
  playwright install chromium

In GitHub Actions:
  pip install playwright && playwright install chromium
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

# Supports negatives (e.g., -19.02%)
MOS_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _extract_mos_from_text(text: str) -> Optional[float]:
    """
    Find MOS near 'Margin of Safety' first, else from an '= xx.xx %' calculation.
    """
    if not text:
        return None

    lower = text.lower()
    idx = lower.find("margin of safety")
    if idx != -1:
        window = text[idx : idx + 700]
        m = MOS_RE.search(window)
        if m:
            return float(m.group(1))

    # Fallback: explicit calculation lines like "= -19.02 %"
    m2 = re.search(r"=\s*([+-]?\d+(?:\.\d+)?)\s*%", text)
    if m2:
        return float(m2.group(1))

    # Last resort: first % anywhere (not ideal)
    m3 = MOS_RE.search(text)
    if m3:
        return float(m3.group(1))

    return None


def get_margin_of_safety_requests(ticker: str, timeout_s: int = 25) -> Optional[float]:
    """
    Fast path: try requests against /stock/{ticker}/dcf.
    May fail with 403 depending on bot protection / geolocation.
    """
    t = ticker.upper().strip()
    url = f"https://www.gurufocus.com/stock/{t}/dcf"

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

    r = requests.get(url, headers=headers, timeout=timeout_s)
    if r.status_code == 403:
        return None
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(separator="\n")
    return _extract_mos_from_text(text)


async def _get_margin_of_safety_playwright_async(
    ticker: str,
    headless: bool = True,
    timeout_ms: int = 45000,
) -> Tuple[Optional[float], str]:
    """
    Browser path: loads the DCF page and extracts MOS from rendered text.
    """
    from playwright.async_api import async_playwright

    t = ticker.upper().strip()
    url = f"https://www.gurufocus.com/stock/{t}/dcf"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # give client-side rendering a moment
        await page.wait_for_timeout(1500)

        text = await page.evaluate("() => document.body && document.body.innerText ? document.body.innerText : ''")

        await ctx.close()
        await browser.close()

    mos = _extract_mos_from_text(text)
    return mos, ("ok" if mos is not None else "mos_not_found")


def get_margin_of_safety(
    ticker: str,
    *,
    prefer_requests: bool = True,
    headless: bool = True,
) -> Optional[float]:
    """
    Sync helper that returns MOS% as float (e.g., 50.43 or -19.02), else None.
    """
    if prefer_requests:
        try:
            mos = get_margin_of_safety_requests(ticker)
            if mos is not None:
                return mos
        except Exception:
            # fall back to playwright
            pass

    mos, _ = asyncio.run(_get_margin_of_safety_playwright_async(ticker, headless=headless))
    return mos
