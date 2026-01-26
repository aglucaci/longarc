import re
from typing import Optional, Tuple
import asyncio

# Matches e.g. "=50.43 %", "50.43%", etc.
#MOS_RE = re.compile(r"=\s*([0-9]+(?:\.[0-9]+)?)\s*%|([0-9]+(?:\.[0-9]+)?)\s*%")
MOS_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")

async def gurufocus_margin_of_safety_playwright(
    ticker: str,
    headless: bool = True,
    timeout_ms: int = 45000,
) -> Tuple[Optional[float], str]:
    """
    Returns (mos_percent, debug_message) for the Earnings-based DCF Margin of Safety.
    Uses a browser context so it works even when requests gets 403.

    Target page:
      https://www.gurufocus.com/stock/{TICKER}/dcf  (or the /term page)
    """
    from playwright.async_api import async_playwright

    ticker = ticker.upper().strip()
    url = f"https://www.gurufocus.com/stock/{ticker}/dcf"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(1500)  # let client rendering settle a bit

        text = await page.evaluate("() => document.body.innerText || ''")

        await ctx.close()
        await browser.close()

    # Strategy: find "Margin of Safety" block, then parse nearest % after it
    idx = text.lower().find("margin of safety")
    if idx != -1:
        window = text[idx : idx + 600]  # local window reduces false matches
        m = MOS_RE.search(window)
        if m:
            val = m.group(1) or m.group(2)
            return float(val), f"Found MOS near 'Margin of Safety' on {url}"

    # Fallback: parse from explicit calculation lines often shown on GuruFocus term pages:
    # "... =(415.62-206.03)/415.62 =50.43 %"
    m2 = re.search(r"=\s*([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if m2:
        return float(m2.group(1)), f"Found MOS from an '=' percentage on {url}"

    return None, f"MOS not found (page layout or access changed): {url}"
    
async def main():
    mos, info = await gurufocus_margin_of_safety_playwright("V")
    print("Margin of Safety:", mos)
    print("Debug:", info)

if __name__ == "__main__":
    asyncio.run(main())
