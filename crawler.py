"""
crawler.py — Elthio
=================================
Fetches supplement product pages via Bright Data Web Unlocker REST API.

Handles:
  - iHerb (anti-bot, JS rendering)
  - LifeExtension (Akamai bypass)
  - Any supplement retailer

Setup:
  Add to your .env file:
    BRIGHTDATA_API_KEY=your_key_here

Usage:
  text = await crawl_page("https://www.iherb.com/pr/...")
  text = await crawl_page("https://www.lifeextension.com/...")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

log = logging.getLogger("elthio.crawler")

load_dotenv(Path(__file__).resolve().parent / ".env")

BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
BRIGHTDATA_ZONE     = "web_unlocker1"
REQUEST_TIMEOUT     = 60


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def crawl_page(url: str, wait_for_selector: Optional[str] = None) -> str:
    """
    Fetch a product page via Bright Data Web Unlocker.
    Returns cleaned page text (brand/title + body). GPT scopes to Supplement Facts.
    """
    api_key = _get_api_key()

    log.info("Bright Data fetch: %s", url)

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.post(
                BRIGHTDATA_ENDPOINT,
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "zone":   BRIGHTDATA_ZONE,
                    "url":    url,
                    "format": "raw",
                },
            )
            r.raise_for_status()
            html = r.text

        if html.strip().startswith("{"):
            try:
                payload = json.loads(html)
                if isinstance(payload, dict) and (
                    payload.get("error") or payload.get("message") or payload.get("status") == "error"
                ):
                    log.error("Bright Data API error body: %s", html[:500])
                    return ""
            except json.JSONDecodeError:
                pass

        if len(html.strip()) < 80:
            log.error("Bright Data returned very short response (%s chars): %s", len(html), html[:200])
            return ""

    except httpx.HTTPStatusError as e:
        log.error("Bright Data HTTP %s for %s", e.response.status_code, url)
        log.error("Response: %s", e.response.text[:300])
        return ""
    except Exception as e:
        log.error("Crawl failed for %s: %s", url, e)
        return ""

    if os.environ.get("DEBUG_HTML"):
        with open("debug_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        log.info("DEBUG HTML saved (%s chars)", len(html))

    return _extract_text(html)


async def screenshot_page(url: str, path: str = "label.png") -> str:
    """
    Screenshots not supported via Web Unlocker REST API.
    Returns empty string — pipeline continues text-only.
    """
    log.info("Screenshot not available — text-only mode.")
    return ""


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text(html: str) -> str:
    """Parse HTML → full-page text so brand/title are present; GPT finds Supplement Facts."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["header", "footer", "nav", "script", "style", "noscript"]):
        tag.decompose()

    # Full page — panel-only scope hid product name/brand above the facts block.
    target = soup
    text = target.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned = text.strip()
    log.info("Extracted %s chars", len(cleaned))
    return cleaned


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.environ.get("BRIGHTDATA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "BRIGHTDATA_API_KEY is not set.\n"
            "Add to your .env file:\n"
            "  BRIGHTDATA_API_KEY=your_key_here"
        )
    return key


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("Usage: python crawler.py <product_url>")
        print()
        print("Examples:")
        print("  python crawler.py 'https://www.iherb.com/pr/now-foods-vitamin-d-3-5000-iu/22335'")
        print("  python crawler.py 'https://www.lifeextension.com/vitamins-supplements/item01913'")
        raise SystemExit(1)

    async def _main() -> None:
        url = sys.argv[1]
        print(f"\nCrawling: {url}\n")
        text = await crawl_page(url)

        if not text:
            print("ERROR: Empty response. Check BRIGHTDATA_API_KEY in .env")
            raise SystemExit(1)

        print(f"Got {len(text):,} chars\n")
        print("-" * 60)
        print(text[:3000])
        if len(text) > 3000:
            print(f"\n... ({len(text)-3000:,} more chars)")

    asyncio.run(_main())
