"""
search_products.py — Elthio
=========================================
Searches iHerb using category browse pages instead of search results.
This returns multiple brands instead of sponsored/featured products.

Category pages sort by bestseller rank and show all brands equally.

Usage:
    from search_products import search_all
    results = await search_all("vitamin d3")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

log = logging.getLogger("elthio.search")

BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
BRIGHTDATA_ZONE = "web_unlocker1"
REQUEST_TIMEOUT = 60

# ─────────────────────────────────────────────────────────────
# iHerb category URL map
# Maps common supplement queries to iHerb category browse pages
# Category pages show all brands sorted by bestseller rank
# ─────────────────────────────────────────────────────────────
IHERB_CATEGORIES = {
    # Vitamin D
    "vitamin d": "https://www.iherb.com/c/vitamin-d?sort=6",
    "vitamin d3": "https://www.iherb.com/c/vitamin-d?sort=6",
    "d3": "https://www.iherb.com/c/vitamin-d?sort=6",
    "cholecalciferol": "https://www.iherb.com/c/vitamin-d?sort=6",
    # Vitamin C
    "vitamin c": "https://www.iherb.com/c/vitamin-c?sort=6",
    "ascorbic acid": "https://www.iherb.com/c/vitamin-c?sort=6",
    # Magnesium
    "magnesium": "https://www.iherb.com/c/magnesium?sort=6",
    "magnesium glycinate": "https://www.iherb.com/c/magnesium?sort=6",
    "magnesium citrate": "https://www.iherb.com/c/magnesium?sort=6",
    # Zinc
    "zinc": "https://www.iherb.com/c/zinc?sort=6",
    "zinc picolinate": "https://www.iherb.com/c/zinc?sort=6",
    # Omega-3
    "omega": "https://www.iherb.com/c/fish-oil-omega-3-6-9?sort=6",
    "omega-3": "https://www.iherb.com/c/fish-oil-omega-3-6-9?sort=6",
    "omega 3": "https://www.iherb.com/c/fish-oil-omega-3-6-9?sort=6",
    "fish oil": "https://www.iherb.com/c/fish-oil-omega-3-6-9?sort=6",
    # Iron
    "iron": "https://www.iherb.com/c/iron?sort=6",
    # Calcium
    "calcium": "https://www.iherb.com/c/calcium?sort=6",
    # B vitamins
    "vitamin b12": "https://www.iherb.com/c/vitamin-b12?sort=6",
    "b12": "https://www.iherb.com/c/vitamin-b12?sort=6",
    "vitamin b": "https://www.iherb.com/c/vitamin-b?sort=6",
    "b complex": "https://www.iherb.com/c/vitamin-b-complex?sort=6",
    # Vitamin K
    "vitamin k": "https://www.iherb.com/c/vitamin-k?sort=6",
    "vitamin k2": "https://www.iherb.com/c/vitamin-k?sort=6",
    "mk-7": "https://www.iherb.com/c/vitamin-k?sort=6",
    # Vitamin E
    "vitamin e": "https://www.iherb.com/c/vitamin-e?sort=6",
    # Vitamin A
    "vitamin a": "https://www.iherb.com/c/vitamin-a?sort=6",
    # CoQ10
    "coq10": "https://www.iherb.com/c/coq10-ubiquinol?sort=6",
    "coenzyme q10": "https://www.iherb.com/c/coq10-ubiquinol?sort=6",
    "ubiquinol": "https://www.iherb.com/c/coq10-ubiquinol?sort=6",
    # Selenium
    "selenium": "https://www.iherb.com/c/selenium?sort=6",
    # Probiotics
    "probiotic": "https://www.iherb.com/c/probiotics?sort=6",
    "probiotics": "https://www.iherb.com/c/probiotics?sort=6",
    # Turmeric / Curcumin
    "curcumin": "https://www.iherb.com/c/curcumin?sort=6",
    "turmeric": "https://www.iherb.com/c/turmeric?sort=6",
    # Melatonin
    "melatonin": "https://www.iherb.com/c/melatonin?sort=6",
    # Multivitamin
    "multivitamin": "https://www.iherb.com/c/multivitamins?sort=6",
    "multi": "https://www.iherb.com/c/multivitamins?sort=6",
    # Collagen
    "collagen": "https://www.iherb.com/c/collagen?sort=6",
    # Ashwagandha
    "ashwagandha": "https://www.iherb.com/c/ashwagandha?sort=6",
    # Biotin
    "biotin": "https://www.iherb.com/c/biotin?sort=6",
    # Copper
    "copper": "https://www.iherb.com/c/copper?sort=6",
    # Folate / Folic Acid
    "folate": "https://www.iherb.com/c/folic-acid?sort=6",
    "folic acid": "https://www.iherb.com/c/folic-acid?sort=6",
    # Iodine
    "iodine": "https://www.iherb.com/c/iodine?sort=6",
}

# Fallback search URL when no category match found
IHERB_SEARCH_URL = "https://www.iherb.com/search?kw={query}&sort=6"

# Curated iHerb products when live scrape is blocked (Bright Data / Cloudflare)
FALLBACK_CATALOG: dict[str, list[dict]] = {
    "magnesium": [
        {
            "name": "Magnesium Bisglycinate Chelate, 60 Veggie Capsules (100 mg per Capsule)",
            "brand": "California Gold Nutrition",
            "price": 9.22,
            "url": "https://www.iherb.com/pr/california-gold-nutrition-magnesium-bisglycinate-chelate-albion-traacs-60-veggie-capsules-100-mg-per-capsule/103273",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
        {
            "name": "Magnesium Bisglycinate Chelate, 240 Veggie Capsules (100 mg per Capsule)",
            "brand": "California Gold Nutrition",
            "price": 28.42,
            "url": "https://www.iherb.com/pr/california-gold-nutrition-magnesium-bisglycinate-chelate-albion-traacs-240-veggie-capsules-100-mg-per-capsule/103274",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
        {
            "name": "Magnesium Glycinate, 180 Tablets",
            "brand": "Doctor's Best",
            "price": 14.99,
            "url": "https://www.iherb.com/pr/doctor-s-best-high-absorption-magnesium-glycinate-lysinate-180-tablets/16567",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
        {
            "name": "Magnesium Glycinate, 120 Tablets",
            "brand": "KAL",
            "price": 11.49,
            "url": "https://www.iherb.com/pr/kal-magnesium-glycinate-400-120-tablets/6185",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
    ],
    "vitamin d": [
        {
            "name": "Vitamin D3, 125 mcg (5,000 IU), 120 Softgels",
            "brand": "NOW Foods",
            "price": 6.81,
            "url": "https://www.iherb.com/pr/now-foods-vitamin-d-3-5000-iu-120-softgels/10421",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
    ],
    "omega-3": [
        {
            "name": "Omega-3 Fish Oil, 180 Softgels",
            "brand": "California Gold Nutrition",
            "price": 12.60,
            "url": "https://www.iherb.com/pr/california-gold-nutrition-omega-3-premium-fish-oil-180-fish-gelatin-softgels/85472",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
    ],
    "coq10": [
        {
            "name": "Ubiquinol, 100 mg, 60 Softgels",
            "brand": "Jarrow Formulas",
            "price": 32.49,
            "url": "https://www.iherb.com/pr/jarrow-formulas-qh-absorb-ubiquinol-100-mg-60-softgels/16567",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
    ],
    "zinc": [
        {
            "name": "Zinc Picolinate, 50 mg, 120 Capsules",
            "brand": "NOW Foods",
            "price": 8.99,
            "url": "https://www.iherb.com/pr/now-foods-zinc-picolinate-50-mg-120-capsules/1343",
            "retailer": "iHerb",
            "retailer_color": "#2D6A4F",
        },
    ],
}


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------


def _fetch_failed(html: str) -> bool:
    if not html or len(html.strip()) < 800:
        return True
    low = html.lower()
    return any(
        x in low
        for x in (
            "request failed",
            "bad_endpoint",
            "not available for immediate access",
            "just a moment",
            "cf-chl",
            "access denied",
        )
    )


def _fallback_products(query: str, max_results: int) -> list[dict]:
    q = query.lower()
    for key, items in FALLBACK_CATALOG.items():
        if key in q or q in key:
            out = []
            for p in items[:max_results]:
                row = dict(p)
                row.setdefault("image", "")
                row.setdefault("rating", "")
                row.setdefault("item_id", "")
                row.setdefault("upc", "")
                row["search_mode"] = "fallback"
                out.append(row)
            if out:
                log.warning("Using fallback catalog for '%s' (%d items)", query, len(out))
                return out
    return []


async def _fetch(url: str) -> str:
    """Fetch any URL via Bright Data Web Unlocker."""
    api_key = os.environ.get("BRIGHTDATA_API_KEY", "")
    if not api_key:
        raise RuntimeError("BRIGHTDATA_API_KEY not set in .env")

    zones = [os.environ.get("BRIGHTDATA_ZONE", BRIGHTDATA_ZONE)]
    alt_zone = os.environ.get("BRIGHTDATA_ZONE_ALT", "").strip()
    if alt_zone and alt_zone not in zones:
        zones.append(alt_zone)

    last_body = ""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for zone in zones:
            try:
                r = await client.post(
                    BRIGHTDATA_ENDPOINT,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json={
                        "zone": zone,
                        "url": url,
                        "format": "raw",
                    },
                )
                r.raise_for_status()
                last_body = r.text
                if not _fetch_failed(last_body):
                    return last_body
                log.warning("Bright Data zone %s returned unusable body for %s", zone, url)
            except Exception as e:
                log.warning("Bright Data fetch (%s): %s", zone, e)

    return last_body


async def fetch_product_upc(url: str) -> str:
    try:
        html = await _fetch(url)
        soup = BeautifulSoup(html, "html.parser")

        # Try data attributes first
        for el in soup.find_all(attrs={"data-ga-upc": True}):
            upc = el.get("data-ga-upc", "").strip()
            if upc and len(upc) >= 10:
                return upc

        for el in soup.find_all(attrs={"data-upc": True}):
            upc = el.get("data-upc", "").strip()
            if upc and len(upc) >= 10:
                return upc

        meta = soup.find("meta", attrs={"property": "product:retailer_item_id"})
        if meta and meta.get("content"):
            upc = str(meta["content"]).strip()
            if upc and len(upc) >= 10:
                return upc

        # Try UPC label text
        upc_match = re.search(r"UPC[:\s]+(\d{10,14})", html)
        if upc_match:
            return upc_match.group(1)

        # Try barcode pattern
        barcode_match = re.search(r'barcode["\s:]+(\d{10,14})', html, re.IGNORECASE)
        if barcode_match:
            return barcode_match.group(1)

        return ""
    except Exception as e:
        log.warning("UPC fetch failed for %s: %s", url, e)
        return ""


# ---------------------------------------------------------------------------
# Category URL resolver
# ---------------------------------------------------------------------------


def _get_category_url(query: str) -> str:
    """
    Find the best matching iHerb category URL for a query.
    Tries exact match first, then partial match.
    Falls back to search URL if no category found.
    """
    q = query.lower().strip()

    if q in IHERB_CATEGORIES:
        log.info("Category match: %s → %s", q, IHERB_CATEGORIES[q])
        return IHERB_CATEGORIES[q]

    for key, url in IHERB_CATEGORIES.items():
        if key in q or q in key:
            log.info("Partial category match: %s → %s", key, url)
            return url

    log.info("No category match for '%s' — using search URL", q)
    return IHERB_SEARCH_URL.format(query=query.replace(" ", "+"))


# ---------------------------------------------------------------------------
# iHerb category page scraper
# ---------------------------------------------------------------------------


async def search_iherb(query: str, max_results: int = 8) -> list[dict]:
    """
    Browse iHerb category page for the given supplement query.
    Returns products from multiple brands sorted by bestseller rank.
    """
    url = _get_category_url(query)
    log.info("Browsing iHerb: %s", url)

    try:
        html = await _fetch(url)
    except Exception as e:
        log.error("iHerb fetch failed: %s", e)
        return _fallback_products(query, max_results)

    if _fetch_failed(html):
        log.error("iHerb fetch blocked or empty for %s — trying fallback catalog", url)
        fallback = _fallback_products(query, max_results)
        if fallback:
            return fallback
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[dict] = []
    seen_urls: set[str] = set()

    cards = (
        soup.select(".product-cell")
        or soup.select("[class*='product-cell']")
        or soup.select(".product")
    )

    log.info("Found %d product cards on category page", len(cards))

    # Walk every card on the page until we collect max_results — category pages are
    # small (~50 cards) and a fixed slice misses products when parsing is sparse.
    for card in cards:
        try:
            p = _parse_iherb_card(card)
            if p and p.get("url"):
                url = str(p["url"]).split("#")[0].rstrip("/")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                products.append(p)
        except Exception as e:
            log.debug("Card parse error: %s", e)
            continue
        if len(products) >= max_results:
            break

    if not products:
        products = _parse_json_ld(soup, max_results)

    if not products:
        products = _extract_iherb_urls(html, max_results)

    products = _filter_relevant(products, query)

    if not products:
        products = _fallback_products(query, max_results)

    log.info("iHerb returned %d relevant products for '%s'", len(products), query)
    return products[:max_results]


def _parse_iherb_card(card) -> Optional[dict]:
    """Parse a single iHerb product card using data-ga-* attributes."""

    link = (
        card.select_one("a.absolute-link")
        or card.select_one("a.product-link")
        or card.select_one("a[href*='/pr/']")
    )
    if not link:
        return None

    url = link.get("href", "")
    if not url.startswith("http"):
        url = "https://www.iherb.com" + url

    brand = (
        link.get("data-ga-brand-name")
        or link.get("data-brand")
        or ""
    )

    price_raw = (
        link.get("data-ga-discount-price")
        or link.get("data-ga-price")
        or link.get("data-price")
        or ""
    )
    price = 0.0
    if price_raw not in (None, ""):
        try:
            price = float(str(price_raw).strip())
        except (TypeError, ValueError):
            price = 0.0

    name = (
        link.get("data-ga-name")
        or link.get("title")
        or link.get("aria-label")
        or ""
    )
    name = name.strip() if name else ""

    if not name:
        name_el = card.select_one(
            ".product-title, [class*='product-title'], [class*='name'], h2, h3"
        )
        name = name_el.get_text(strip=True) if name_el else ""

    if not brand:
        brand_el = card.select_one(
            ".product-subtitle, [class*='brand'], [class*='subtitle'], .brand"
        )
        brand = brand_el.get_text(strip=True) if brand_el else ""

    if not price:
        price_el = card.select_one(".price, [class*='price'], .sale-price")
        price = _parse_price(price_el.get_text(strip=True) if price_el else "")

    img_el = card.select_one("img")
    image = (img_el.get("src") or img_el.get("data-src", "")) if img_el else ""

    item_id_m = re.search(r"/(\d+)$", url)
    item_id = item_id_m.group(1) if item_id_m else ""

    upc = ""
    for attr in ("data-ga-upc", "data-upc", "data-barcode"):
        val = (link.get(attr) or "").strip()
        if val and len(val) >= 10:
            upc = val
            break

    if not name and not brand:
        return None

    return {
        "name": name,
        "brand": brand,
        "price": price,
        "url": url,
        "image": image,
        "rating": "",
        "item_id": item_id,
        "upc": upc,
        "retailer": "iHerb",
        "retailer_color": "#2D6A4F",
    }


def _extract_iherb_urls(html: str, max_results: int) -> list[dict]:
    """Last resort — extract product URLs from raw HTML."""
    products = []
    seen: set[str] = set()
    patterns = [
        r'href="(https://www\.iherb\.com/pr/[^"]+)"',
        r"href='(https://www\.iherb\.com/pr/[^']+)'",
        r'href="(/pr/[^"]+)"',
    ]
    urls: list[str] = []
    for pat in patterns:
        urls.extend(re.findall(pat, html))
    for raw in urls:
        url = raw if raw.startswith("http") else f"https://www.iherb.com{raw}"
        if url not in seen and len(products) < max_results:
            seen.add(url)
            slug = url.split("/pr/")[-1].split("/")[0]
            name = slug.replace("-", " ").title()
            products.append(
                {
                    "name": name,
                    "brand": "",
                    "price": 0.0,
                    "url": url,
                    "image": "",
                    "rating": "",
                    "item_id": url.split("/")[-1],
                    "upc": "",
                    "retailer": "iHerb",
                    "retailer_color": "#2D6A4F",
                }
            )
        if len(products) >= max_results:
            break
    return products


def _filter_relevant(products: list[dict], query: str) -> list[dict]:
    """
    Filter products to only those relevant to the query.
    Keeps products where name or brand contains at least
    one meaningful word from the query.
    """
    stopwords = {
        "the",
        "and",
        "with",
        "for",
        "of",
        "in",
        "a",
        "an",
        "to",
        "from",
        "by",
        "as",
        "or",
        "is",
        "it",
        "its",
        "plus",
        "extra",
        "high",
        "best",
        "pure",
        "natural",
    }
    raw_words = [w.lower() for w in re.split(r"\W+", query) if w]
    query_words: set[str] = set()
    for w in raw_words:
        if w in stopwords:
            continue
        if len(w) >= 2 or re.match(r"^[a-z]\d+$", w, re.I):
            query_words.add(w)

    if not query_words:
        return products

    relevant = []
    for p in products:
        combined = (p.get("name", "") + " " + p.get("brand", "")).lower()
        if any(t in combined for t in query_words):
            relevant.append(p)

    return relevant if relevant else products


# ---------------------------------------------------------------------------
# LifeExtension — direct URL audit only (search not reliable)
# LifeExtension search API returns irrelevant results regardless of query.
# Users can paste LifeExtension URLs directly in the URL input box.
# TODO: identify correct LifeExtension search API format
# ---------------------------------------------------------------------------


async def search_lifeextension(query: str, max_results: int = 5) -> list[dict]:
    """LifeExtension search disabled — returns empty list."""
    log.info("LifeExtension search disabled — use direct URL audit instead")
    return []


# ---------------------------------------------------------------------------
# Combined search
# ---------------------------------------------------------------------------


async def search_all(query: str, max_per_retailer: int = 8) -> list[dict]:
    """
    Search iHerb category pages for supplements.
    Returns multi-brand results sorted by bestseller rank.
    LifeExtension products can be added via direct URL.
    """
    results = await search_iherb(query, max_results=max_per_retailer)
    log.info("search_all returning %d results for '%s'", len(results), query)
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_price(text: str) -> float:
    text = text.replace(",", "")
    match = re.search(r"\$?([\d]+\.?\d*)", text)
    if match:
        try:
            val = float(match.group(1))
            if 1 < val < 500:
                return val
        except ValueError:
            pass
    return 0.0


def _unwrap_json_ld_item(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    if item.get("@type") == "ListItem" and isinstance(item.get("item"), dict):
        return item["item"]
    return item


def _parse_json_ld(soup: BeautifulSoup, max_results: int) -> list[dict]:
    """Extract products from Schema.org JSON-LD."""
    products: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items: list[Any] = []
            if isinstance(data, list):
                items = data
            elif data.get("@type") == "ItemList":
                items = data.get("itemListElement", [])
            elif data.get("@type") == "Product":
                items = [data]

            for raw in items:
                item = _unwrap_json_ld_item(raw)
                if not isinstance(item, dict):
                    continue
                if item.get("@type") not in ("Product",) and "/pr/" not in str(item.get("url", "")):
                    continue
                offer = item.get("offers", {})
                url = item.get("url", "")
                if isinstance(offer, list) and offer:
                    offer = offer[0]
                if not url or "/pr/" not in url:
                    continue
                brand = item.get("brand", {})
                brand_name = brand.get("name", "") if isinstance(brand, dict) else str(brand)
                price_val = 0.0
                if isinstance(offer, dict) and offer.get("price") not in (None, ""):
                    try:
                        price_val = float(offer.get("price", 0))
                    except (TypeError, ValueError):
                        price_val = 0.0
                products.append(
                    {
                        "name": item.get("name", ""),
                        "brand": brand_name,
                        "price": price_val,
                        "url": url,
                        "image": item.get("image", "") if isinstance(item.get("image"), str) else "",
                        "rating": "",
                        "item_id": "",
                        "upc": item.get("gtin13") or item.get("gtin") or "",
                        "retailer": "iHerb",
                        "retailer_color": "#2D6A4F",
                    }
                )
                if len(products) >= max_results:
                    break
        except Exception:
            continue
        if len(products) >= max_results:
            break
    return products


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "vitamin d3"

    async def _main():
        print(f"\nBrowsing iHerb category for: '{query}'\n")
        results = await search_all(query)
        if not results:
            print("No results found.")
            return
        print(f"{len(results)} products found:\n")
        for i, p in enumerate(results, 1):
            price = f"${p['price']:.2f}" if p["price"] else "N/A"
            print(f"  {i}. {p['brand']} — {p['name']}")
            print(f"     Price: {price} | {p['url'][:65]}")
            print()

    asyncio.run(_main())
