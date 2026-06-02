"""
pipeline.py — Elthio (Unified)
==========================================
Single entry point: crawl → GPT-4o structured extract → NIH DSLD (dsld.py) → reconcile → golden_record.json

Usage:
  set OPENAI_API_KEY
  python pipeline.py "https://www.iherb.com/pr/now-foods-vitamin-d-3-2000-iu/678"
  python pipeline.py "https://www.iherb.com/pr/..." "733739003737"   # optional UPC — aborts if scrape mismatch
  python pipeline.py "https://www.lifeextension.com/vitamins-supplements/item01913/vitamin-d3"
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process

import dsld
from crawler import crawl_page, screenshot_page

# Load environment variables from .env next to this file (not only cwd)
load_dotenv(Path(__file__).resolve().parent / ".env")

# Quieter NIH module when run from pipeline
dsld.DEBUG = False

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("elthio")

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or None)

FUZZY_THRESHOLD = 45


# ---------------------------------------------------------------------------
# Canonical models
# ---------------------------------------------------------------------------


class Ingredient(BaseModel):
    name: str = Field(..., description="Standardized ingredient name")
    amount: Optional[float] = None
    unit: Optional[str] = None
    form: Optional[str] = None
    percent_dv: Optional[float] = None


class SupplementProduct(BaseModel):
    brand: str
    product_name: str
    serving_size: Optional[str] = None
    servings_per_container: Optional[int] = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    other_ingredients: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    warnings: Optional[str] = None
    suggested_use: Optional[str] = None
    dsld_id: Optional[str] = None
    upc: Optional[str] = None
    price: Optional[float] = None
    url: str = ""
    extraction_confidence: float = 0.0


class NihIngredient(BaseModel):
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    daily_value_pct: Optional[float] = None


class NihProduct(BaseModel):
    dsld_id: str
    name: str
    brand: str
    ingredients: list[NihIngredient] = Field(default_factory=list)


@dataclass
class AuditEntry:
    name: str
    retail_amount: Optional[float]
    retail_unit: Optional[str]
    nih_amount: Optional[float]
    nih_unit: Optional[str]
    status: str
    confidence: float
    diff: str


@dataclass
class GoldenRecord:
    product_name: str
    brand: str
    upc: Optional[str]
    dsld_id: str
    source_url: str
    extraction_confidence: float
    servings_per_container: Optional[int] = None
    price: Optional[float] = None
    audit: list[AuditEntry] = field(default_factory=list)
    overall_status: str = "UNVERIFIED"

    def to_dict(self) -> dict:
        return asdict(self)


UNIT_TO_MCG: dict[str, float] = {
    "mcg": 1.0,
    "µg": 1.0,
    "ug": 1.0,
    "mg": 1000.0,
    "g": 1_000_000.0,
}

#
# IU conversions are substance-specific.
#
IU_TO_MCG: dict[str, float] = {
    "vitamin d": 0.025,  # 1 IU Vitamin D = 0.025 mcg
    "vitamin d3": 0.025,
    "vitamin a": 0.3,  # 1 IU Vitamin A = 0.3 mcg
    "vitamin e": 0.67,  # 1 IU Vitamin E = 0.67 mcg
}


def _to_mcg(amount: float, unit: Optional[str]) -> Optional[float]:
    if not unit:
        return None
    u = unit.lower().strip()
    factor = UNIT_TO_MCG.get(u)
    return amount * factor if factor is not None else None


def _iu_to_mcg(amount: float, ingredient_name: str) -> Optional[float]:
    """Convert IU -> mcg using substance hints from ingredient_name."""
    name_lower = (ingredient_name or "").lower()
    for key, factor in IU_TO_MCG.items():
        if key in name_lower:
            return amount * factor
    return None


def _extract_price(text: str) -> Optional[float]:
    """Extract product price from crawled text using dollar amounts.

    Finds all values like $12.99, keeps amounts in a plausible retail band,
    then picks the best iHerb-style **bottle** price: prefer $8--$60, then
    the lowest amount at least $5. Do **not** return amounts under $5 as the
    product price — those are usually per-serving, add-ons, or wrong lines
    (the real list price is often in JS and missing from the crawl). If
    nothing qualifies, return None so the UI can ask for price manually.
    """
    if not text:
        return None
    pattern = r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
    amounts: list[float] = []
    for m in re.finditer(pattern, text):
        try:
            amounts.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    if not amounts:
        return None
    # Plausible retail supplement prices only
    filtered = [a for a in amounts if 1.0 <= a <= 200.0]
    if not filtered:
        return None
    iherb_main = [a for a in filtered if 8.0 <= a <= 60.0]
    if iherb_main:
        return min(iherb_main)
    at_least_5 = [a for a in filtered if a >= 5.0]
    if at_least_5:
        return min(at_least_5)
    # No candidate >= $5 — do not return min of small amounts (per-serving / teaser lines).
    return None


def _servings_from_url(url: str) -> Optional[int]:
    """Infer bottle count from common retailer URL slugs (e.g. iHerb ...240-softgels...)."""
    if not url:
        return None
    u = url.lower()
    patterns = [
        r"(\d{2,4})[-_]softgels?(?:[/-]|$)",
        r"(\d{2,4})[-_]caps?(?:ules)?(?:[/-]|$)",
        r"(\d{2,4})[-_]tabs?(?:lets)?(?:[/-]|$)",
        r"(\d{2,4})[-_]gummies?(?:[/-]|$)",
        r"(\d{2,4})[-_]count(?:[/-]|$)",
        r"(\d{2,4})[-_]servings?(?:[/-]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, u)
        if m:
            try:
                n = int(m.group(1))
                if 10 <= n <= 9999:
                    return n
            except ValueError:
                pass
    return None


STATUS_ICONS = {
    "MATCH": "OK",
    "MISMATCH": "XX",
    "MISSING_NIH": "NIH?",
    "MISSING_RETAIL": "RET?",
    "UNCERTAIN": "??",
    "VERIFIED": "OK",
    "INCOMPLETE": "INC",
    "UNVERIFIED": "--",
}


def _overall_status(audit: list[AuditEntry]) -> str:
    statuses = {e.status for e in audit}
    if "MISMATCH" in statuses:
        return "MISMATCH"
    if {"MISSING_NIH", "MISSING_RETAIL"} & statuses:
        return "INCOMPLETE"
    if "UNCERTAIN" in statuses:
        return "UNCERTAIN"
    if audit and all(e.status == "MATCH" for e in audit):
        return "VERIFIED"
    return "UNVERIFIED"


_SYSTEM_PROMPT = (
    "You are an expert at extracting dietary supplement facts from web pages and labels. "
    "Return only valid JSON matching the schema. "
    "Extract EVERY ingredient in the Supplement Facts table. "
    "For amount use a float; for unit use lowercase: mg, mcg, g, iu, % or null. "
    "If brand or product name cannot be determined from text, infer it from context "
    "such as URLs, image alt text, or page titles. "
    "Never return 'Unknown' — make your best inference."
)


async def extract_with_gpt4o(
    text: str,
    screenshot_path: Optional[str] = None,
) -> SupplementProduct:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract supplement facts from this page:\n\n{text[:12000]}"},
    ]

    if screenshot_path and os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Supplement Facts label screenshot — use to verify or complete ingredients.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
                    },
                ],
            }
        )
        log.info("Vision: screenshot attached")
    else:
        log.info("Vision: text only")

    response = await client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=messages,
        response_format=SupplementProduct,
        temperature=0.0,
    )
    product = response.choices[0].message.parsed
    assert product is not None
    log.info("Extracted: %s — %s (%s ingredients)", product.brand, product.product_name, len(product.ingredients))
    return product


def _parse_nih_rows(label: dict) -> list[NihIngredient]:
    rows = label.get("ingredientRows") or label.get("dietaryIngredients") or []
    result: list[NihIngredient] = []
    for row in rows:
        if isinstance(row, str):
            continue
        name = (row.get("name") or row.get("ingredientName") or "").strip()
        if not name:
            continue
        qty = row.get("quantity") or []
        if isinstance(qty, dict):
            qty = [qty]
        amount = None
        unit = None
        if qty:
            raw = qty[0].get("quantity")
            try:
                amount = float(str(raw).replace(",", "")) if raw is not None else None
            except (ValueError, TypeError):
                amount = None
            u = qty[0].get("unit")
            unit = u.lower().strip() if u else None
        dv_pct = None
        dv_raw = row.get("dailyValue") or row.get("percentDailyValue")
        if dv_raw is not None:
            try:
                dv_pct = float(str(dv_raw).replace("%", "").strip())
            except (ValueError, TypeError):
                pass
        result.append(
            NihIngredient(name=name, amount=amount, unit=unit, daily_value_pct=dv_pct)
        )
    return result


def fetch_nih_product(query: str) -> Optional[NihProduct]:
    log.info("NIH query: %r", query)
    hits = dsld.search_products(query)
    if not hits:
        return None
    for i, h in enumerate(hits):
        log.info("  [%s] %s | %s | ID: %s", i, h.get("name"), h.get("brand"), h.get("id"))
    # Prefer brand match to avoid mismatching similarly named products.
    # Query is typically: "{brand} {product_name}". Brand can contain spaces
    # (e.g. "Life Extension"), so we take a few leading non-numeric tokens.
    brand_hint = ""
    brand_matched = []
    if query:
        tokens = query.split()
        brand_tokens: list[str] = []
        for t in tokens:
            if any(ch.isdigit() for ch in t):
                break
            brand_tokens.append(t)
            if len(brand_tokens) >= 3:
                break
        brand_hint = " ".join(brand_tokens).strip()

    if brand_hint:
        bh = brand_hint.lower()
        for h in hits:
            b = (h.get("brand") or "").lower()
            if bh in b:
                brand_matched.append(h)

    best = brand_matched[0] if brand_matched else hits[0]
    lid = str(best["id"])
    label = dsld.get_label(lid)
    if not label:
        log.error("No label for DSLD ID %s", lid)
        return None
    return NihProduct(
        dsld_id=lid,
        name=best.get("name") or "",
        brand=best.get("brand") or "",
        ingredients=_parse_nih_rows(label),
    )


# Normalize common ingredient name variations (retail vs NIH DSLD wording)
SYNONYMS: dict[str, str] = {
    "vitamin d3 (cholecalciferol)": "vitamin d3",
    "vitamin d (as d3 cholecalciferol)": "vitamin d3",
    "cholecalciferol": "vitamin d3",
    "ascorbic acid": "vitamin c",
    "tocopherol": "vitamin e",
    "retinol": "vitamin a",
    "thiamine": "vitamin b1",
    "riboflavin": "vitamin b2",
    "pyridoxine": "vitamin b6",
    "cobalamin": "vitamin b12",
    "folate": "folic acid",
}


def _normalize_name(name: str) -> str:
    key = name.lower().strip()
    return SYNONYMS.get(key, key)


def reconcile(retail: list[Ingredient], nih: list[NihIngredient]) -> list[AuditEntry]:
    audit: list[AuditEntry] = []
    nih_names = [i.name for i in nih]
    matched_nih: set[int] = set()

    for r_ing in retail:
        if not nih_names:
            audit.append(
                AuditEntry(
                    name=r_ing.name,
                    retail_amount=r_ing.amount,
                    retail_unit=r_ing.unit,
                    nih_amount=None,
                    nih_unit=None,
                    status="MISSING_NIH",
                    confidence=0.0,
                    diff="No NIH ingredients",
                )
            )
            continue

        result = process.extractOne(
            _normalize_name(r_ing.name),
            [_normalize_name(n) for n in nih_names],
            scorer=fuzz.token_sort_ratio,
        )
        if not result or result[1] < FUZZY_THRESHOLD:
            audit.append(
                AuditEntry(
                    name=r_ing.name,
                    retail_amount=r_ing.amount,
                    retail_unit=r_ing.unit,
                    nih_amount=None,
                    nih_unit=None,
                    status="MISSING_NIH",
                    confidence=(result[1] / 100.0) if result else 0.0,
                    diff="Not found in NIH label",
                )
            )
            continue

        _match, score, nih_idx = result
        matched_nih.add(nih_idx)
        n_ing = nih[nih_idx]
        confidence = score / 100.0
        status, diff = _classify_dosage(
            r_ing.amount,
            r_ing.unit,
            n_ing.amount,
            n_ing.unit,
            ingredient_name=r_ing.name,
        )
        if confidence < 0.90 and status == "MATCH":
            status = "UNCERTAIN"
            diff = f"Fuzzy name ({score:.0f}%) — {diff}"
        audit.append(
            AuditEntry(
                name=r_ing.name,
                retail_amount=r_ing.amount,
                retail_unit=r_ing.unit,
                nih_amount=n_ing.amount,
                nih_unit=n_ing.unit,
                status=status,
                confidence=confidence,
                diff=diff,
            )
        )

    for idx, n_ing in enumerate(nih):
        if idx not in matched_nih:
            audit.append(
                AuditEntry(
                    name=n_ing.name,
                    retail_amount=None,
                    retail_unit=None,
                    nih_amount=n_ing.amount,
                    nih_unit=n_ing.unit,
                    status="MISSING_RETAIL",
                    confidence=1.0,
                    diff="In NIH label but not matched on retail page",
                )
            )
    return audit


def _classify_dosage(
    r_amt: Optional[float],
    r_unit: Optional[str],
    n_amt: Optional[float],
    n_unit: Optional[str],
    ingredient_name: str = "",
) -> tuple[str, str]:
    if r_amt is None or n_amt is None:
        if r_amt is None and n_amt is None:
            return "MATCH", "No quantified amount on both"
        return "UNCERTAIN", f"Retail={r_amt} {r_unit} | NIH={n_amt} {n_unit}"

    r_u = (r_unit or "").lower().strip().rstrip("s").rstrip("()")
    n_u = (n_unit or "").lower().strip().rstrip("s").rstrip("()")
    if r_u == n_u:
        delta = r_amt - n_amt
        pct = abs(delta) / n_amt * 100 if n_amt else 0
        if abs(delta) < 0.01:
            return "MATCH", f"{r_amt} {r_unit} matches NIH"
        st = "MISMATCH" if pct > 5 else "MATCH"
        return st, f"delta {delta:+.2f} ({pct:.1f}% vs NIH)"

    r_mcg = _to_mcg(r_amt, r_u)
    n_mcg = _to_mcg(n_amt, n_u)
    if r_mcg is None or n_mcg is None:
        # Try IU conversion if one side is IU.
        if r_u == "iu" and r_mcg is None:
            r_mcg = _iu_to_mcg(r_amt, ingredient_name)
        if n_u == "iu" and n_mcg is None:
            n_mcg = _iu_to_mcg(n_amt, ingredient_name)

        # Still not convertible? mark uncertain.
        if r_mcg is None or n_mcg is None:
            return "UNCERTAIN", f"Units differ: retail={r_amt} {r_unit} NIH={n_amt} {n_unit}"

    delta_mcg = r_mcg - n_mcg
    pct = abs(delta_mcg) / n_mcg * 100 if n_mcg else 0
    if pct < 2:
        return "MATCH", f"~equal after mcg conversion (delta {delta_mcg:+.0f} mcg)"
    return "MISMATCH", f"{pct:.1f}% off after mcg conversion"


def print_report(record: GoldenRecord) -> None:
    icon = STATUS_ICONS.get(record.overall_status, "?")
    w = 72
    print("\n" + "=" * w)
    print(f"  {icon}  BIO-LOGIC AUDIT REPORT")
    print("=" * w)
    print(f"  Product      : {record.product_name}")
    print(f"  Brand        : {record.brand}")
    print(f"  UPC          : {record.upc or 'N/A'}")
    print(f"  DSLD ID      : {record.dsld_id}")
    print(f"  Confidence   : {record.extraction_confidence:.0%}")
    print(f"  Overall      : {record.overall_status}")
    print("-" * w)
    for e in record.audit:
        ico = STATUS_ICONS.get(e.status, "?")
        diff = e.diff if len(e.diff) <= 50 else e.diff[:47] + "..."
        print(f"  {ico} {e.status:<14} {e.name:<28} {e.confidence * 100:>5.0f}%  {diff}")
    print("=" * w + "\n")


def _validate_product_url(url: str) -> tuple[bool, str]:
    """Reject category/search URLs — audits need a single product detail page."""
    u = (url or "").strip()
    if not u.startswith("http"):
        return False, "URL must start with https:// (paste a full product link)."
    low = u.lower()
    if "iherb.com" in low:
        if "/pr/" not in low:
            return False, (
                "That looks like an iHerb category or search link, not a product page. "
                "Use Search → Audit on one product, or paste a URL containing /pr/ "
                "(example: https://www.iherb.com/pr/now-foods-vitamin-d-3-5000-iu/22335)."
            )
    if "lifeextension.com" in low and "/item" not in low and "/vitamins-supplements/" not in low:
        return False, (
            "Use a direct Life Extension product URL (path usually contains /item…), not a category page."
        )
    return True, ""


async def run_audit(
    url: str,
    expected_upc: Optional[str] = None,
    max_retries: int = 3,
) -> tuple[Optional[GoldenRecord], str]:
    """
    Returns (record, err). On success, err is an empty string.
    """
    if not os.getenv("OPENAI_API_KEY"):
        log.error("Set OPENAI_API_KEY")
        return None, (
            "OPENAI_API_KEY is not set. Add it to the .env file in this project folder (required to read the label)."
        )

    if not os.getenv("BRIGHTDATA_API_KEY"):
        log.error("Set BRIGHTDATA_API_KEY")
        return None, (
            "BRIGHTDATA_API_KEY is not set. The crawler needs Bright Data Web Unlocker to fetch iHerb / Life Extension pages. "
            "Add the key to your .env (see comments at the top of crawler.py)."
        )

    log.info("Starting audit: %s", url)

    ok_url, url_err = _validate_product_url(url)
    if not ok_url:
        log.error("Invalid audit URL: %s", url)
        return None, url_err

    # Delete stale screenshot before retries to prevent bleed between runs.
    try:
        if os.path.exists("label.png"):
            os.remove("label.png")
    except Exception:
        pass

    product: Optional[SupplementProduct] = None
    extracted_price: Optional[float] = None
    last_fail = (
        "Could not complete the audit. Check the product URL, .env API keys, and try again."
    )

    for attempt in range(1, max_retries + 1):
        log.info("Attempt %s/%s: %s", attempt, max_retries, url)

        try:
            results = await asyncio.gather(
                crawl_page(url),
                screenshot_page(url, path="label.png"),
                return_exceptions=True,
            )
        except Exception as e:
            log.error("Crawl failed: %s", e)
            last_fail = f"Page fetch failed: {e}"
            continue

        text_result, screenshot_result = results[0], results[1]

        text = ""
        if isinstance(text_result, Exception):
            log.error("Crawl failed: %s", text_result)
            last_fail = f"Page fetch failed: {text_result}"
            continue
        text = text_result

        screenshot_path = "label.png"
        if isinstance(screenshot_result, Exception):
            log.error("Screenshot failed: %s", screenshot_result)
            screenshot_path = ""
        else:
            screenshot_path = screenshot_result or ""

        if not text.strip():
            if not os.path.exists("label.png"):
                log.warning("Empty crawl — retrying...")
                last_fail = (
                    "The product page came back with no text. Check BRIGHTDATA_API_KEY and the URL "
                    "(use a direct product page, not a search results link)."
                )
                continue
            log.warning("Empty crawl text; extraction will rely on vision screenshot")

        log.info("Crawled %s chars | %s", len(text), screenshot_path or "(no screenshot)")
        extracted_price = _extract_price(text)
        if extracted_price is not None:
            log.info("Extracted page price: $%.2f", extracted_price)

        vision_path = screenshot_path if screenshot_path and os.path.exists(screenshot_path) else None
        if vision_path is None and os.path.exists("label.png"):
            try:
                os.remove("label.png")
                log.info("Cleared stale screenshot (no valid capture this run)")
            except OSError:
                pass

        try:
            product = await extract_with_gpt4o(text, vision_path)
        except Exception as e:
            log.error("GPT extraction failed: %s", e)
            last_fail = f"Label extraction failed (OpenAI): {e}"
            continue

        if not product.ingredients:
            log.warning("No ingredients extracted — retrying...")
            last_fail = (
                "No supplement facts / ingredients were found on the page. The listing may be incomplete, "
                "or the page did not load fully."
            )
            continue

        if expected_upc:
            if not product.upc:
                log.warning(
                    "Expected UPC %s but none extracted on attempt %s — retrying...",
                    expected_upc,
                    attempt,
                )
                last_fail = (
                    f"You required UPC {expected_upc}, but the page did not show a matching barcode. "
                    "Clear the UPC field or check the product page."
                )
                await asyncio.sleep(2)
                continue
            if product.upc.replace("-", "") != expected_upc.replace("-", ""):
                log.warning(
                    "UPC mismatch on attempt %s (got %s, expected %s) — retrying...",
                    attempt,
                    product.upc,
                    expected_upc,
                )
                last_fail = (
                    f"UPC mismatch: page shows {product.upc}, you expected {expected_upc}."
                )
                await asyncio.sleep(2)
                continue
            log.info("UPC verified: %s ✅", product.upc)

        log.info("Correct product confirmed on attempt %s", attempt)
        break

    else:
        log.error(
            "Failed to get correct product after %s attempts — flag for manual review",
            max_retries,
        )
        return None, last_fail

    assert product is not None

    product.url = url
    product.price = extracted_price
    product.extraction_confidence = 0.88
    if product.servings_per_container is None:
        inferred = _servings_from_url(url)
        if inferred is not None:
            product.servings_per_container = inferred
            log.info("Inferred servings_per_container=%s from URL", inferred)

    query = product.upc or f"{product.brand} {product.product_name}"
    nih = fetch_nih_product(query)
    if nih is None and product.upc:
        nih = fetch_nih_product(f"{product.brand} {product.product_name}")
    if nih is None:
        log.warning("No NIH DSLD match — cannot reconcile")
        tried = f"UPC {product.upc}" if product.upc else f'"{product.brand} {product.product_name}"'
        return None, (
            "No match in the NIH ODS Dietary Supplement Label Database (DSLD) for "
            f"{tried}. Not every retail product is listed. Try the 12-digit UPC from the bottle in the UPC field, "
            "or a different product URL. If the product is new or store-brand, it may not be in DSLD yet."
        )

    log.info("NIH: %s — %s (DSLD %s)", nih.brand, nih.name, nih.dsld_id)
    audit_entries = reconcile(product.ingredients, nih.ingredients)

    record = GoldenRecord(
        product_name=product.product_name,
        brand=product.brand,
        upc=product.upc,
        servings_per_container=product.servings_per_container,
        price=getattr(product, "price", None),
        dsld_id=nih.dsld_id,
        source_url=url,
        extraction_confidence=product.extraction_confidence,
        audit=audit_entries,
        overall_status=_overall_status(audit_entries),
    )
    print_report(record)
    return record, ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <url> [expected_upc]")
        sys.exit(1)

    url = sys.argv[1]
    expected_upc = sys.argv[2] if len(sys.argv) > 2 else None

    async def _main() -> None:
        record, err = await run_audit(url, expected_upc=expected_upc)
        if record:
            out = "golden_record.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
            log.info("Saved %s", out)
        else:
            log.error("%s", err)
            print(err, file=sys.stderr)
            sys.exit(1)

    asyncio.run(_main())
