"""
price_monitor.py — Elthio Search-Based Price Monitor Agent

Architecture: supplement names → retailer search → Claude extracts
top N results → NIH check via dsld.py → upsert to Supabase.

Zero hardcoded URLs. Scales automatically as retailers update listings.
API-ready: set source_type='api' on any retailer row and the agent
routes to that retailer's API instead of scraping.

Run:           python price_monitor.py
Single supp:   python price_monitor.py --supplement "magnesium glycinate"
Single retail: python price_monitor.py --retailer iherb
Search DB:     python price_monitor.py --search "coq10"
Full run:      python price_monitor.py --run-all
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
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

ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
BRIGHTDATA_API_KEY  = os.environ.get("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_ZONE     = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker1")
BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
SCRAPERAPI_KEY      = os.environ.get("SCRAPERAPI_KEY", "")
ZENROWS_API_KEY     = os.environ.get("ZENROWS_API_KEY", "")
SUPABASE_URL        = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY        = (
    os.environ.get("SUPABASE_KEY", "")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
).strip()
CLAUDE_MODEL        = "claude-sonnet-4-5-20250929"

JS_RETAILERS = {"iherb", "vitacost", "amazon"}
REQUEST_DELAY_SECONDS = 2.0
MAX_RESULTS_PER_SEARCH = 5


def _rest_base() -> str:
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL must be set")
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1"


def _get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
            ),
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _sh() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation,resolution=merge-duplicates",
    }


def supa_get(table: str, params: dict) -> list:
    url = f"{_rest_base()}/{table}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_sh())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()) or []


def supa_upsert(table: str, row: dict) -> None:
    url  = f"{_rest_base()}/{table}?on_conflict=affiliate_url"
    data = json.dumps(row).encode()
    req  = urllib.request.Request(url, data=data, headers=_sh(), method="POST")
    urllib.request.urlopen(req, timeout=15)


def load_supplements() -> list[dict]:
    return supa_get("tracked_supplements", {"active": "eq.true", "select": "*"})


def load_retailers() -> list[dict]:
    return supa_get("retailers", {
        "active": "eq.true",
        "select": "*",
        "order":  "priority.asc",
    })


def _fetch_brightdata_html(url: str) -> str:
    if not BRIGHTDATA_API_KEY:
        return ""
    body = json.dumps({"zone": BRIGHTDATA_ZONE, "url": url, "format": "raw"}).encode()
    req = urllib.request.Request(
        BRIGHTDATA_ENDPOINT,
        data=body,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            html = r.read().decode(errors="replace")
        if html.strip().startswith("{"):
            try:
                payload = json.loads(html)
                if isinstance(payload, dict) and (
                    payload.get("error") or payload.get("message") or payload.get("status") == "error"
                ):
                    log.warning("Bright Data API error: %s", html[:300])
                    return ""
            except json.JSONDecodeError:
                pass
        if len(html.strip()) < 500:
            return ""
        log.info("BrightData: %d chars", len(html))
        return html[:2_000_000]
    except Exception as e:
        log.warning("BrightData failed: %s", e)
        return ""


def fetch_page(url: str, retailer: str) -> str:
    """Fetch rendered HTML via Bright Data, ScraperAPI, ZenRows, or plain HTTP."""
    html = _fetch_brightdata_html(url)
    if html:
        return html

    if SCRAPERAPI_KEY:
        try:
            render  = "true" if retailer in JS_RETAILERS else "false"
            api_url = (
                f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}"
                f"&url={urllib.parse.quote(url)}&render={render}&premium=true"
            )
            html = _get(api_url, timeout=45).decode(errors="replace")
            if len(html) > 2000:
                log.info("ScraperAPI: %d chars", len(html))
                return html[:2_000_000]
        except Exception as e:
            log.warning("ScraperAPI failed: %s", e)

    if ZENROWS_API_KEY:
        try:
            api_url = (
                f"https://api.zenrows.com/v1/?apikey={ZENROWS_API_KEY}"
                f"&url={urllib.parse.quote(url)}&js_render=true&premium_proxy=true"
            )
            html = _get(api_url, timeout=45).decode(errors="replace")
            if len(html) > 2000:
                log.info("ZenRows: %d chars", len(html))
                return html[:2_000_000]
        except Exception as e:
            log.warning("ZenRows failed: %s", e)

    if retailer not in JS_RETAILERS:
        try:
            html = _get(url, timeout=20).decode(errors="replace")
            log.info("Plain HTTP: %d chars", len(html))
            return html[:2_000_000]
        except Exception as e:
            log.warning("Plain HTTP failed: %s", e)

    return ""


def preprocess_html(html: str, query: str) -> str:
    """Extract price-relevant signals from raw HTML before sending to Claude."""
    parts: list[str] = []

    for match in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    ):
        try:
            data = json.loads(match.strip())
            items: list = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]
            elif isinstance(data, dict):
                items = [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                type_ = item.get("@type", "")
                if isinstance(type_, list):
                    type_ = " ".join(type_)
                if any(t in type_ for t in ("Product", "Offer", "ItemPage", "ItemList")):
                    parts.append(f"JSON-LD:\n{json.dumps(item, indent=2)[:4000]}")
                    break
        except Exception:
            continue

    og = re.findall(
        r'<meta[^>]*property=["\']og:([^"\']+)["\'][^>]*content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if og:
        parts.append("OG TAGS:\n" + "\n".join(f"og:{k}: {v}" for k, v in og[:15]))

    t = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if t:
        parts.append(f"TITLE: {t.group(1).strip()[:200]}")

    prices: list[str] = []
    for pat in [
        r'"price"\s*:\s*"?(\d+\.?\d*)"?',
        r'itemprop=["\']price["\'][^>]*content=["\']([^"\']+)["\']',
        r'data-price=["\'](\d+\.?\d*)["\']',
        r"\$\s*(\d+\.\d{2})",
        r'class=["\'][^"\']*price[^"\']*["\'][^>]*>\$?\s*(\d+\.\d{2})',
    ]:
        prices.extend(re.findall(pat, html, re.IGNORECASE)[:5])
    if prices:
        parts.append(f"PRICES FOUND: {list(dict.fromkeys(prices))[:15]}")

    product_blocks = re.findall(
        r"(?:product-title|product-name|product_title|item-name)"
        r"[^>]*>([^<]{10,100})",
        html, re.IGNORECASE
    )
    if product_blocks:
        parts.append(
            "PRODUCT NAMES IN RESULTS:\n"
            + "\n".join(f"- {p.strip()}" for p in product_blocks[:10])
        )

    sf = re.search(r"(Supplement Facts.{0,2000})", html, re.IGNORECASE | re.DOTALL)
    if sf:
        parts.append(f"SUPPLEMENT FACTS:\n{sf.group(1)[:1500]}")

    sv = re.search(r"(Servings?\s+Per\s+Container[^\n]{0,100})", html, re.IGNORECASE)
    if sv:
        parts.append(f"SERVINGS: {sv.group(1).strip()}")

    if parts:
        result = "\n\n---\n\n".join(parts)
        log.info(
            "Preprocessed: %d chars from %d MB HTML",
            len(result), len(html) // 1_000_000,
        )
        return result[:15000]

    log.warning("No structured data found — using first 10k chars")
    return html[:10000]


def extract_products_from_search(
    html: str,
    supplement_name: str,
    retailer: str,
    search_query: str,
    max_results: int = MAX_RESULTS_PER_SEARCH,
) -> list[dict]:
    """Extract multiple products from a retailer search results page."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    preprocessed = preprocess_html(html, search_query)

    system = f"""You are a supplement price extraction agent for Elthio.
You receive HTML from a retailer's search results page and extract
the top {max_results} most relevant products.

Return ONLY valid JSON array — no markdown, no explanation:
[
  {{
    "product_title": "exact product name",
    "brand": "brand name",
    "price_usd": 19.99,
    "serving_size": "1 capsule",
    "servings": 120,
    "cost_per_serving": 0.17,
    "form": "glycinate|citrate|ubiquinol|etc",
    "in_stock": true,
    "product_url": "full URL if visible",
    "match_confidence": "high|medium|low",
    "rank": 1
  }}
]

Rules:
- Return up to {max_results} products, best match ranked 1
- match_confidence high = clearly matches '{supplement_name}'
- match_confidence medium = probably matches, some ambiguity
- match_confidence low = might match but uncertain
- SKIP products that are clearly unrelated (hair pins, cotton tampons, etc)
- price_usd: number only, no $ sign, null if not found
- cost_per_serving: price_usd / servings, 4 decimal places
- form: specific chemical form if visible (glycinate not just magnesium)
- product_url: full URL if visible in HTML, otherwise null
- If fewer than {max_results} matching products exist, return fewer
- Return [] if no relevant products found"""

    prompt = (
        f"Retailer: {retailer}\n"
        f"Searching for: {supplement_name}\n"
        f"Search query used: {search_query}\n\n"
        f"Page data:\n{preprocessed}\n\n"
        f"Extract up to {max_results} matching products."
    )

    body = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 2000,
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
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())

    raw = resp["content"][0]["text"].strip()
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
    result = json.loads(raw)
    return result if isinstance(result, list) else []


def run_nih_check(product_title: str, brand: str) -> dict:
    try:
        from dsld import search_products
        from rapidfuzz import fuzz

        query   = f"{brand} {product_title}".strip() if brand else product_title
        results = search_products(query)
        if not results:
            return {"nih_status": "NOT_FOUND", "nih_confidence": 0, "nih_dsld_id": None}

        best     = results[0]
        nih_name = best.get("name") or best.get("product_name") or ""
        score    = fuzz.token_sort_ratio(query.lower(), nih_name.lower())
        status   = "VERIFIED" if score >= 80 else "POSSIBLE" if score >= 60 else "UNCERTAIN"
        return {
            "nih_status":     status,
            "nih_confidence": int(score),
            "nih_dsld_id":    str(best.get("id", "")),
        }
    except ImportError:
        return {"nih_status": "UNVERIFIED", "nih_confidence": 0, "nih_dsld_id": None}
    except Exception as e:
        log.warning("NIH check error: %s", e)
        return {"nih_status": "ERROR", "nih_confidence": 0, "nih_dsld_id": None}


def build_affiliate_url(url: str, retailer_tag: str) -> str:
    if not url or not retailer_tag:
        return url or ""
    sep = "&" if "?" in url else "?"
    return url + sep + retailer_tag.lstrip("?&")


def fetch_via_api(supplement: dict, retailer: dict) -> list[dict]:
    """Placeholder for official retailer APIs."""
    name = retailer["name"]
    if name == "iherb":
        raise NotImplementedError("iHerb API not yet configured — add IHERB_API_KEY to env")
    if name == "amazon":
        raise NotImplementedError("Amazon PAAPI not yet configured")
    if name == "thorne":
        raise NotImplementedError("Thorne API not yet configured")
    raise NotImplementedError(f"No API adapter for {name}")


def _parse_search_terms(supplement: dict) -> list[str]:
    search_terms = supplement.get("search_terms") or [supplement["name"]]
    if isinstance(search_terms, str):
        search_terms = json.loads(search_terms)
    return search_terms if isinstance(search_terms, list) else [supplement["name"]]


def monitor_supplement_retailer(supplement: dict, retailer: dict) -> list[dict]:
    """Fetch search results for one supplement from one retailer."""
    supp_name     = supplement["name"]
    search_terms  = _parse_search_terms(supplement)
    retailer_name = retailer["name"]
    source_type   = retailer.get("source_type", "scrape")
    affiliate_tag = retailer.get("affiliate_tag", "")
    search_url_t  = retailer.get("search_url", "") or ""
    used_query    = search_terms[0] if search_terms else supp_name

    log.info("▶ %s @ %s [%s]", supp_name, retailer_name, source_type)

    products: list[dict] = []

    if source_type == "api":
        try:
            products = fetch_via_api(supplement, retailer)
            log.info("  API: %d products", len(products))
        except NotImplementedError as e:
            log.warning("  %s — falling back to scrape", e)
            source_type = "scrape"

    if source_type in ("scrape", "api_pending") and not products:
        html = ""
        for term in search_terms:
            if not search_url_t:
                break
            search_url = search_url_t.replace("{query}", urllib.parse.quote(term))
            log.info("  Searching: %s", search_url[:80])
            html = fetch_page(search_url, retailer_name)
            if len(html) > 3000:
                used_query = term
                break
            time.sleep(REQUEST_DELAY_SECONDS)

        if not html or len(html) < 3000:
            log.warning("  No usable HTML for %s @ %s", supp_name, retailer_name)
            return []

        try:
            products = extract_products_from_search(
                html, supp_name, retailer_name, used_query
            )
            log.info("  Claude extracted %d products", len(products))
        except Exception as e:
            log.error("  Extraction failed: %s", e)
            return []

    products = [
        p for p in products
        if p.get("match_confidence") in ("high", "medium")
        and p.get("price_usd")
        and float(p.get("price_usd") or 0) > 0
    ]

    if not products:
        log.warning("  No high/medium confidence products with prices")
        return []

    upserted: list[dict] = []
    for i, product in enumerate(products[:MAX_RESULTS_PER_SEARCH]):
        price    = product.get("price_usd")
        servings = product.get("servings")
        cpp      = product.get("cost_per_serving")
        if price and servings and not cpp:
            cpp = round(float(price) / int(servings), 4)

        prod_url = product.get("product_url") or ""
        if not prod_url and search_url_t:
            prod_url = search_url_t.replace(
                "{query}", urllib.parse.quote(used_query)
            )
        aff_url = build_affiliate_url(prod_url, affiliate_tag) if prod_url else ""
        if not aff_url:
            log.warning("  No URL for product %d — skipping", i + 1)
            continue

        nih = run_nih_check(
            product.get("product_title", supp_name),
            product.get("brand", ""),
        )

        row = {
            "supplement_name":  supp_name,
            "brand":            product.get("brand"),
            "product_title":    product.get("product_title"),
            "retailer":         retailer_name,
            "price_usd":        float(price) if price else None,
            "serving_size":     product.get("serving_size"),
            "servings":         int(servings) if servings else None,
            "cost_per_serving": cpp,
            "form":             product.get("form"),
            "in_stock":         product.get("in_stock", True),
            "affiliate_url":    aff_url,
            "source_type":      source_type,
            "search_query":     used_query,
            "rank_in_results":  i + 1,
            "nih_status":       nih["nih_status"],
            "nih_confidence":   int(nih["nih_confidence"] or 0),
            "nih_dsld_id":      nih["nih_dsld_id"],
            "last_checked":     datetime.now(timezone.utc).isoformat(),
        }

        try:
            supa_upsert("product_prices", row)
            log.info(
                "  OK Rank %d: %s — $%.2f (NIH: %s)",
                i + 1,
                (product.get("product_title") or "?")[:40],
                float(price or 0),
                nih["nih_status"],
            )
            upserted.append(row)
        except Exception as e:
            log.error("  Supabase upsert failed: %s", e)

        time.sleep(REQUEST_DELAY_SECONDS)

    return upserted


def run_monitor(
    supplement_filter: str | None = None,
    retailer_filter: str | None = None,
) -> dict:
    """Run monitor for all supplements × all retailers."""
    supplements = load_supplements()
    retailers   = load_retailers()

    if supplement_filter:
        supplements = [
            s for s in supplements
            if supplement_filter.lower() in s["name"].lower()
        ]
    if retailer_filter:
        retailers = [
            r for r in retailers
            if r["name"].lower() == retailer_filter.lower()
        ]

    log.info(
        "Monitor run: %d supplements × %d retailers = %d combinations",
        len(supplements), len(retailers), len(supplements) * len(retailers),
    )

    total_products = 0
    success = skipped = failed = 0

    for supp in supplements:
        for retailer in retailers:
            try:
                results = monitor_supplement_retailer(supp, retailer)
                if results:
                    total_products += len(results)
                    success += 1
                else:
                    skipped += 1
            except Exception as e:
                log.error("FAIL %s @ %s: %s", supp["name"], retailer["name"], e)
                failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)

    summary = {
        "supplements":    len(supplements),
        "retailers":      len(retailers),
        "combinations":   len(supplements) * len(retailers),
        "success":        success,
        "skipped":        skipped,
        "failed":         failed,
        "total_products": total_products,
    }
    log.info("Monitor complete: %s", summary)
    return summary


def search_prices(
    query: str,
    retailer: str | None = None,
    form: str | None = None,
    max_price: float | None = None,
    sort: str = "cost_per_serving",
    verified_only: bool = False,
) -> list[dict]:
    allowed_sort = {"cost_per_serving", "price_usd", "last_checked", "rank_in_results"}
    if sort not in allowed_sort:
        sort = "cost_per_serving"

    params: dict = {
        "supplement_name": f"ilike.*{query.lower().strip()}*",
        "in_stock":        "eq.true",
        "select":          "*",
        "order":           f"{sort}.asc.nullslast,rank_in_results.asc.nullslast",
        "limit":           "100",
    }
    if retailer:
        params["retailer"] = f"eq.{retailer}"
    if verified_only:
        params["nih_status"] = "eq.VERIFIED"

    try:
        try:
            results = supa_get("product_prices", params)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "rank_in_results" in params.get("order", ""):
                params["order"] = f"{sort}.asc.nullslast"
                results = supa_get("product_prices", params)
            else:
                raise
        if form:
            results = [
                r for r in results
                if form.lower() in (r.get("form") or "").lower()
            ]
        if max_price:
            results = [
                r for r in results
                if (r.get("price_usd") or 0) <= max_price
            ]
        return results
    except Exception as e:
        log.error("search_prices error: %s", e)
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elthio Price Monitor")
    parser.add_argument("--supplement", help="Monitor one supplement (name filter)")
    parser.add_argument("--retailer",   help="Monitor one retailer only")
    parser.add_argument("--search",     help="Search the price database")
    parser.add_argument("--run-all",    action="store_true")
    parser.add_argument("--list",       action="store_true",
                        help="List all tracked supplements and retailers")
    args = parser.parse_args()

    if args.list:
        print("\nTracked supplements:")
        for s in load_supplements():
            print(f"  {s['name']} — {s.get('category', '')}")
        print("\nActive retailers:")
        for r in load_retailers():
            print(f"  {r['name']} ({r['display_name']}) [{r['source_type']}]")

    elif args.search:
        results = search_prices(args.search)
        if not results:
            print("No results.")
        else:
            print(f"\n{'Product':<35} {'Retailer':<16} {'Price':>7} {'$/serv':>8} {'NIH':<12}")
            print("-" * 85)
            for r in results[:20]:
                print(
                    f"{(r.get('product_title') or '')[:34]:<35} "
                    f"{r.get('retailer', '')[:15]:<16} "
                    f"${r.get('price_usd') or 0:>6.2f} "
                    f"${r.get('cost_per_serving') or 0:>7.4f} "
                    f"{r.get('nih_status', ''):<12}"
                )
            print(f"\nTotal: {len(results)} results")

    elif args.run_all or args.supplement or args.retailer:
        summary = run_monitor(args.supplement, args.retailer)
        print(f"\n{'=' * 50}")
        print("Monitor complete:")
        print(f"  {summary['supplements']} supplements x {summary['retailers']} retailers")
        print(f"  {summary['total_products']} products upserted")
        print(
            f"  {summary['success']} success / "
            f"{summary['skipped']} skipped / {summary['failed']} failed"
        )
        print(f"{'=' * 50}")

    else:
        print("\n" + "=" * 60)
        print("  PRICE MONITOR — SELF TEST")
        print("=" * 60)

        print("\n[1] Supabase connection + supplements loaded")
        try:
            supps = load_supplements()
            rets  = load_retailers()
            print(f"  OK {len(supps)} supplements, {len(rets)} retailers")
        except Exception as e:
            print(f"  FAIL {e}")
            supps, rets = [], []

        print("\n[2] List supplements")
        try:
            for s in supps[:5]:
                print(f"     {s['name']} ({s.get('category', '')})")
            if len(supps) > 5:
                print(f"     ... and {len(supps) - 5} more")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n[3] NIH check")
        try:
            nih = run_nih_check("Vitamin D3 5000 IU", "NOW Foods")
            print(f"  OK {nih['nih_status']} ({nih['nih_confidence']}%)")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n[4] Single supplement test (Life Extension, vitamin d3)")
        try:
            supps_d3 = [s for s in supps if "vitamin d3" == s["name"].lower()]
            rets_le  = [r for r in rets if r["name"] == "life_extension"]
            if supps_d3 and rets_le:
                results = monitor_supplement_retailer(supps_d3[0], rets_le[0])
                print(f"  OK {len(results)} products upserted")
                for r in results[:3]:
                    print(
                        f"     {(r.get('product_title') or '?')[:40]} — "
                        f"${r.get('price_usd', 0):.2f} (NIH: {r.get('nih_status')})"
                    )
            else:
                print("  WARN vitamin d3 or life_extension not in DB — run search_monitor.sql")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n[5] Price search")
        try:
            results = search_prices("vitamin d3")
            print(f"  OK {len(results)} results for 'vitamin d3'")
        except Exception as e:
            print(f"  FAIL {e}")

        print("\n" + "=" * 60)
        print("  Run with --run-all to monitor all supplements")
        print("  Run with --list to see all supplements + retailers")
        print("  Run with --search 'coq10' to query the database")
        print("=" * 60 + "\n")
