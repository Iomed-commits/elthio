"""
price_monitor.py — Elthio + Biologer Price Monitor Agent

Fetches retailer product pages, uses Claude to extract price/serving data,
runs the existing pipeline.py NIH reconciliation for ingredient verification,
and upserts everything into Supabase product_prices.

Reuses: pipeline.py reconciliation engine, crawler.py fetch layer,
        dsld.py NIH lookup — zero duplication.

Run manually:   python price_monitor.py
Railway cron:   0 2 * * *  (every night 2am UTC)
Single URL:     python price_monitor.py --url "https://..." --retailer iherb --name "vitamin c"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from supabase_client import normalize_supabase_url

# ── Environment ───────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SCRAPERAPI_KEY    = os.environ.get("SCRAPERAPI_KEY", "")
ZENROWS_API_KEY   = os.environ.get("ZENROWS_API_KEY", "")
SUPABASE_URL      = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY      = (
    os.environ.get("SUPABASE_KEY", "")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
).strip()
CLAUDE_MODEL      = "claude-sonnet-4-5-20250929"

# ── Affiliate tags per retailer ───────────────────────────────────────────────
AFFILIATE_TAGS: dict[str, str] = {
    "iherb":          "?rcode=ELTHIO",
    "life_extension": "?source=elthio",
    "thorne":         "?affId=ELTHIO",
    "vitacost":       "?affId=ELTHIO",
    "swanson":        "?srccode=ELTHIO",
}

# ── Retailers that need JS rendering (ScraperAPI render=true) ─────────────────
JS_RETAILERS = {"iherb", "amazon", "vitacost"}


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get_json(url: str, headers: dict | None = None, timeout: int = 10) -> Any:
    req = urllib.request.Request(
        url, headers={**(headers or {}), "User-Agent": "Elthio/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _post_json(url: str, body: dict, headers: dict | None = None) -> Any:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={**(headers or {}), "Content-Type": "application/json",
                 "User-Agent": "Elthio/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ── Supabase helpers ──────────────────────────────────────────────────────────
def _supa_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation,resolution=merge-duplicates",
    }


def supa_get(table: str, params: dict) -> list:
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_supa_headers())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()) or []


def supa_upsert(table: str, row: dict) -> dict:
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}?on_conflict=affiliate_url"
    result = _post_json(url, row, headers=_supa_headers())
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    return row


def supa_patch(table: str, params: dict, body: dict) -> None:
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data, headers=_supa_headers(), method="PATCH"
    )
    urllib.request.urlopen(req, timeout=10)


# ── Page fetcher — ScraperAPI / ZenRows / plain HTTP ─────────────────────────
def fetch_page(url: str, retailer: str) -> str:
    """
    Fetch rendered HTML for a product page.
    Priority order:
    1. ScraperAPI (best for iHerb + Life Extension — returns full rendered HTML)
    2. ZenRows fallback
    3. Plain HTTP last resort (Life Extension only)
    Skips crawler.py entirely — Bright Data text-only mode returns
    cross-sell content instead of the target product HTML.
    """
    # 1. ScraperAPI — primary for all retailers
    if SCRAPERAPI_KEY:
        try:
            render   = "true" if retailer in JS_RETAILERS else "false"
            api_url  = (
                f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}"
                f"&url={urllib.parse.quote(url)}"
                f"&render={render}"
                f"&premium=true"
            )
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                text = r.read().decode(errors="replace")
                if len(text) > 2000:
                    log.info("ScraperAPI: %d chars for %s", len(text), retailer)
                    return text[:20000]
                else:
                    log.warning("ScraperAPI returned short page (%d chars) — trying fallback", len(text))
        except Exception as e:
            log.warning("ScraperAPI failed: %s", e)

    # 2. ZenRows fallback
    if ZENROWS_API_KEY:
        try:
            api_url = (
                f"https://api.zenrows.com/v1/?apikey={ZENROWS_API_KEY}"
                f"&url={urllib.parse.quote(url)}"
                f"&js_render=true"
                f"&premium_proxy=true"
            )
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                text = r.read().decode(errors="replace")
                if len(text) > 2000:
                    log.info("ZenRows: %d chars for %s", len(text), retailer)
                    return text[:20000]
        except Exception as e:
            log.warning("ZenRows failed: %s", e)

    # 3. Plain HTTP — last resort, only works for Life Extension
    if retailer not in JS_RETAILERS:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode(errors="replace")
                log.info("Plain HTTP: %d chars for %s", len(text), retailer)
                return text[:20000]
        except Exception as e:
            log.warning("Plain HTTP failed: %s", e)

    log.error("All fetch methods failed for %s", url)
    return ""


# ── Claude extraction ─────────────────────────────────────────────────────────
def extract_price_data(html: str, supplement_name: str, retailer: str) -> dict:
    """
    Use Claude to extract price and product data from raw page HTML/text.
    Returns structured dict or empty dict on failure.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    system = """You are a supplement product data extractor.
Extract pricing and product information from retail page HTML.
Return ONLY valid JSON — no markdown, no explanation, no backticks:
{
  "product_title": "exact product name from page",
  "brand": "brand name",
  "price_usd": 19.99,
  "serving_size": "1 capsule",
  "servings": 120,
  "cost_per_serving": 0.17,
  "form": "glycinate|citrate|ascorbic acid|ubiquinol|etc",
  "in_stock": true,
  "primary_ingredient": "main active ingredient name exactly as on label"
}
Rules:
- price_usd: numeric only, no $ sign
- servings: integer, the servings per container
- cost_per_serving: price_usd / servings, rounded to 4 decimal places
- form: the specific chemical form of the supplement if shown
- in_stock: true unless page shows out of stock / sold out
- If a field cannot be found, use null
- Never guess or invent values"""

    prompt = (
        f"Retailer: {retailer}\n"
        f"Supplement we expect: {supplement_name}\n"
        f"IMPORTANT: Extract ONLY the primary product on this page — ignore "
        f"related products, recommendations, bundles, or cross-sells anywhere "
        f"on the page. The product title must clearly match '{supplement_name}'. "
        f"If the main product does not match '{supplement_name}', return null "
        f"for price_usd and set product_title to whatever IS on the page so "
        f"we can debug it.\n\n"
        f"Page content (first 10000 chars — may be raw HTML):\n"
        f"Focus only on the MAIN product section. Ignore nav, footer, "
        f"recommendations, and anything not about '{supplement_name}'.\n"
        f"If you see HTML tags like <title>, <h1>, <span class='price'>, "
        f"use those as primary signals.\n\n"
        f"{html[:10000]}\n\n"
        f"Extract the product data."
    )

    body = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 512,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
    raw = resp["content"][0]["text"].strip()
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


# ── NIH verification — reuses dsld.py lookup ────────────────────────────────
def run_nih_check(product_title: str, brand: str) -> dict:
    """
    Reuse dsld.py NIH DSLD lookup and fuzzy matching.
    Returns { nih_status, nih_confidence, nih_dsld_id }.
    """
    try:
        from dsld import search_products
        from rapidfuzz import fuzz

        query   = f"{brand} {product_title}" if brand else product_title
        results = search_products(query)
        if not results:
            return {"nih_status": "NOT_FOUND", "nih_confidence": 0, "nih_dsld_id": None}

        best    = results[0]
        dsld_id = str(best.get("id", ""))
        nih_name = best.get("name") or best.get("product_name") or ""
        score    = fuzz.token_sort_ratio(query.lower(), nih_name.lower())
        nih_status = "VERIFIED" if score >= 80 else "POSSIBLE" if score >= 60 else "UNCERTAIN"

        return {
            "nih_status":     nih_status,
            "nih_confidence": score,
            "nih_dsld_id":    dsld_id,
        }
    except ImportError:
        log.debug("dsld.py not importable — skipping NIH check")
        return {"nih_status": "UNVERIFIED", "nih_confidence": 0, "nih_dsld_id": None}
    except Exception as e:
        log.warning("NIH check failed: %s", e)
        return {"nih_status": "ERROR", "nih_confidence": 0, "nih_dsld_id": None}


# ── Affiliate URL builder ─────────────────────────────────────────────────────
def build_affiliate_url(url: str, retailer: str, custom_tag: str | None = None) -> str:
    tag = custom_tag or AFFILIATE_TAGS.get(retailer, "")
    if not tag:
        return url
    separator = "&" if "?" in url else "?"
    return url + separator + tag.lstrip("?&")


# ── Single URL monitor ────────────────────────────────────────────────────────
def monitor_url(
    url: str,
    retailer: str,
    supplement_name: str,
    affiliate_tag: str | None = None,
) -> dict:
    """Monitor one product URL: fetch, extract, NIH-check, upsert to Supabase."""
    log.info("Monitoring: %s [%s] %s", supplement_name, retailer, url)

    html = fetch_page(url, retailer)
    if not html:
        raise ValueError(f"Could not fetch {url}")

    extracted = extract_price_data(html, supplement_name, retailer)
    log.info(
        "Extracted: %s — $%.2f / %d servings",
        extracted.get("product_title", "?"),
        extracted.get("price_usd") or 0,
        extracted.get("servings") or 0,
    )

    nih = run_nih_check(
        extracted.get("product_title", supplement_name),
        extracted.get("brand", ""),
    )
    log.info("NIH status: %s (confidence: %d%%)", nih["nih_status"], nih["nih_confidence"])

    aff_url = build_affiliate_url(url, retailer, affiliate_tag)

    price    = extracted.get("price_usd")
    servings = extracted.get("servings")
    cpp      = extracted.get("cost_per_serving")
    if price and servings and not cpp:
        cpp = round(float(price) / int(servings), 4)

    row = {
        "supplement_name":  supplement_name.lower().strip(),
        "brand":            extracted.get("brand"),
        "product_title":    extracted.get("product_title"),
        "retailer":         retailer,
        "price_usd":        price,
        "serving_size":     extracted.get("serving_size"),
        "servings":         servings,
        "cost_per_serving": cpp,
        "form":             extracted.get("form"),
        "in_stock":         extracted.get("in_stock", True),
        "affiliate_url":    aff_url,
        "source_type":      "scraped",
        "nih_status":       nih["nih_status"],
        "nih_confidence":   int(nih["nih_confidence"] or 0),
        "nih_dsld_id":      nih["nih_dsld_id"],
        "last_checked":     datetime.now(timezone.utc).isoformat(),
    }

    supa_upsert("product_prices", row)

    try:
        supa_patch(
            "monitor_urls",
            {"url": f"eq.{url}"},
            {"last_run": row["last_checked"], "last_status": nih["nih_status"]},
        )
    except Exception:
        pass

    return row


# ── Batch monitor — all active URLs ──────────────────────────────────────────
def run_monitor() -> dict:
    """Run the full monitor: fetch all active monitor_urls, process each one."""
    try:
        urls = supa_get("monitor_urls", {"active": "eq.true", "select": "*"})
    except Exception as e:
        log.error("Could not load monitor_urls from Supabase: %s", e)
        return {"error": str(e)}

    log.info("Starting monitor run: %d URLs", len(urls))
    success = failed = 0

    for entry in urls:
        url             = entry.get("url", "")
        retailer        = entry.get("retailer", "")
        supplement_name = entry.get("supplement_name", "")
        affiliate_tag   = entry.get("affiliate_tag")

        if not url or not retailer or not supplement_name:
            log.warning("Skipping invalid entry: %s", entry)
            failed += 1
            continue

        try:
            result = monitor_url(url, retailer, supplement_name, affiliate_tag)
            log.info(
                "✅ %s @ %s — $%.2f (NIH: %s)",
                supplement_name, retailer,
                result.get("price_usd") or 0,
                result.get("nih_status"),
            )
            success += 1
        except Exception as e:
            log.error("❌ Failed %s @ %s: %s", supplement_name, retailer, e)
            failed += 1

    summary = {"success": success, "failed": failed, "total": len(urls)}
    log.info("Monitor complete: %s", summary)
    return summary


# ── Price search — for Elthio search UI ──────────────────────────────────────
def search_prices(
    query: str,
    retailer: str | None = None,
    form: str | None = None,
    max_price: float | None = None,
    sort: str = "cost_per_serving",
) -> list[dict]:
    """Search product_prices by supplement name."""
    allowed_sort = {"cost_per_serving", "price_usd", "last_checked"}
    if sort not in allowed_sort:
        sort = "cost_per_serving"

    params: dict = {
        "supplement_name": f"ilike.*{query.lower().strip()}*",
        "in_stock":        "eq.true",
        "select":          "*",
        "order":           f"{sort}.asc.nullslast",
        "limit":           "50",
    }
    if retailer:
        params["retailer"] = f"eq.{retailer}"

    try:
        results = supa_get("product_prices", params)
        if form:
            results = [r for r in results if form.lower() in (r.get("form") or "").lower()]
        if max_price:
            results = [r for r in results if (r.get("price_usd") or 0) <= max_price]
        return results
    except Exception as e:
        log.error("search_prices error: %s", e)
        return []


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elthio Price Monitor")
    parser.add_argument("--url",        help="Single URL to monitor")
    parser.add_argument("--retailer",   help="Retailer name (iherb, life_extension, etc.)")
    parser.add_argument("--name",       help="Supplement name")
    parser.add_argument("--search",     help="Search the database")
    parser.add_argument("--run-all",    action="store_true", help="Run full monitor")
    args = parser.parse_args()

    if args.search:
        print(f"\nSearching for '{args.search}'...")
        results = search_prices(args.search)
        if not results:
            print("No results found.")
        else:
            print(f"\n{'Brand':<20} {'Retailer':<16} {'Form':<16} {'Price':>7} {'$/serv':>8} {'NIH':<12}")
            print("-" * 85)
            for r in results:
                print(
                    f"{(r.get('brand') or '')[:19]:<20} "
                    f"{r.get('retailer','')[:15]:<16} "
                    f"{(r.get('form') or '')[:15]:<16} "
                    f"${r.get('price_usd') or 0:>6.2f} "
                    f"${r.get('cost_per_serving') or 0:>7.4f} "
                    f"{r.get('nih_status',''):<12}"
                )

    elif args.url and args.retailer and args.name:
        result = monitor_url(args.url, args.retailer, args.name)
        print(json.dumps(result, indent=2, default=str))

    elif args.run_all:
        summary = run_monitor()
        print(f"\nDone: {summary}")

    else:
        print("\n" + "=" * 60)
        print("  PRICE MONITOR — SELF TEST")
        print("=" * 60)

        print("\n[1] Test Claude extraction (Life Extension Vitamin D3)")
        try:
            sample = """
            Life Extension Vitamin D3 5000 IU
            Item #: 01913
            Price: $8.00
            Serving Size: 1 Softgel
            Servings Per Container: 60
            Form: Cholecalciferol
            In Stock
            """
            result = extract_price_data(sample, "vitamin d3", "life_extension")
            print(f"  OK {result.get('product_title')} — ${result.get('price_usd')} / {result.get('servings')} servings")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n[2] Test NIH check")
        try:
            nih = run_nih_check("Vitamin D3 5000 IU", "Life Extension")
            print(f"  OK NIH status: {nih['nih_status']} (confidence: {nih['nih_confidence']}%)")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n[3] Test affiliate URL builder")
        url = build_affiliate_url(
            "https://www.lifeextension.com/vitamins-supplements/item01913/vitamin-d3",
            "life_extension"
        )
        print(f"  OK {url}")

        print("\n[4] Test Supabase connection")
        try:
            rows = supa_get("monitor_urls", {"active": "eq.true", "select": "url,retailer,supplement_name", "limit": "3"})
            print(f"  OK {len(rows)} active monitor URLs found")
            for r in rows:
                print(f"     {r.get('supplement_name')} @ {r.get('retailer')}")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n[5] Test price search")
        try:
            results = search_prices("vitamin d3")
            print(f"  OK {len(results)} results for 'vitamin d3'")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n" + "=" * 60)
        print("  Run with --run-all to monitor all URLs")
        print("  Run with --search 'vitamin c' to query database")
        print("=" * 60 + "\n")
