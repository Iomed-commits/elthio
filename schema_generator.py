"""
schema_generator.py — Elthio
==========================================
Converts a Elthio Golden Record into Schema.org structured data.

Outputs:
  - JSON-LD (for embedding in web pages)
  - HTML page with embedded markup (ready to publish)
  - Standalone .jsonld file (for APIs and feeds)

Usage:
  python schema_generator.py golden_record.json
  python schema_generator.py golden_record.json --html
  python schema_generator.py golden_record.json --feed  # batch mode from folder
"""

from __future__ import annotations

import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Elthio Schema Version
# ---------------------------------------------------------------------------
ELTHIO_SCHEMA_VERSION = "1.0"
ELTHIO_CONTEXT = "https://elthio.health/schema/v1"   # your future domain
BASE_SCHEMA_URL  = "https://schema.org"


# ---------------------------------------------------------------------------
# Core converter
# ---------------------------------------------------------------------------

def golden_record_to_jsonld(record: dict) -> dict:
    """
    Convert a Elthio Golden Record dict into a Schema.org JSON-LD object.
    Uses schema.org/Product as base + custom Elthio extensions.
    """
    audit = record.get("audit", [])
    verified_ingredients = [
        e for e in audit
        if e.get("status") in ("MATCH", "UNCERTAIN")
        and e.get("retail_amount") is not None
    ]

    # Build ingredient list
    ingredients_ld = []
    for ing in verified_ingredients:
        ing_obj = {
            "@type": "dietarySupplement",
            "name": ing["name"],
            "elthio:verificationStatus": ing["status"],
            "elthio:matchConfidence": round(ing.get("confidence", 0), 2),
        }
        if ing.get("retail_amount"):
            ing_obj["amount"] = f"{ing['retail_amount']} {ing.get('retail_unit', '')}".strip()
        if ing.get("nih_amount"):
            ing_obj["elthio:nihVerifiedAmount"] = f"{ing['nih_amount']} {ing.get('nih_unit', '')}".strip()
        ingredients_ld.append(ing_obj)

    # Build the full JSON-LD
    now = datetime.now(timezone.utc).isoformat()
    record_hash = _hash_record(record)

    jsonld = {
        "@context": {
            "@vocab": BASE_SCHEMA_URL + "/",
            "elthio": ELTHIO_CONTEXT + "#",
            "schema": BASE_SCHEMA_URL + "/",
        },
        "@type": "Product",
        "@id": f"https://elthio.health/records/{record.get('dsld_id', 'unknown')}",

        # Core product identity
        "name": record.get("product_name", "Unknown Product"),
        "brand": {
            "@type": "Brand",
            "name": record.get("brand", "Unknown Brand"),
        },
        "identifier": [
            {
                "@type": "PropertyValue",
                "propertyID": "UPC",
                "value": record.get("upc"),
            } if record.get("upc") else None,
            {
                "@type": "PropertyValue",
                "propertyID": "NIH_DSLD_ID",
                "value": record.get("dsld_id"),
            },
            {
                "@type": "PropertyValue",
                "propertyID": "ELTHIO_RECORD_HASH",
                "value": record_hash,
            },
        ],
        "url": record.get("source_url", ""),

        # Supplement-specific
        "category": "Dietary Supplement",
        "hasMerchantReturnPolicy": None,

        # Verified ingredients
        "nutrition": {
            "@type": "NutritionInformation",
            "elthio:verifiedIngredients": ingredients_ld,
            "elthio:totalIngredients": len(audit),
            "elthio:verifiedCount": len(verified_ingredients),
        },

        # Elthio verification metadata
        "elthio:verification": {
            "@type": "elthio:VerificationRecord",
            "elthio:overallStatus": record.get("overall_status", "UNVERIFIED"),
            "elthio:dsldId": record.get("dsld_id"),
            "elthio:recordHash": record_hash,
            "elthio:verifiedAt": now,
            "elthio:schemaVersion": ELTHIO_SCHEMA_VERSION,
            "elthio:extractionConfidence": record.get("extraction_confidence", 0),
            "elthio:auditSummary": _build_audit_summary(audit),
        },

        # SEO / search engine fields
        "description": _build_description(record, verified_ingredients),
        "additionalProperty": _build_additional_properties(record, audit),
    }

    # Clean None values
    jsonld["identifier"] = [i for i in jsonld["identifier"] if i]
    return jsonld


def _hash_record(record: dict) -> str:
    """SHA-256 hash of the canonical record for tamper detection."""
    canonical = json.dumps({
        "product_name": record.get("product_name"),
        "brand": record.get("brand"),
        "dsld_id": record.get("dsld_id"),
        "audit": record.get("audit", []),
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _build_audit_summary(audit: list[dict]) -> dict:
    statuses = [e.get("status") for e in audit]
    return {
        "MATCH":           statuses.count("MATCH"),
        "MISMATCH":        statuses.count("MISMATCH"),
        "MISSING_NIH":     statuses.count("MISSING_NIH"),
        "MISSING_RETAIL":  statuses.count("MISSING_RETAIL"),
        "UNCERTAIN":       statuses.count("UNCERTAIN"),
    }


def _build_description(record: dict, verified: list[dict]) -> str:
    status = record.get("overall_status", "UNVERIFIED")
    brand = record.get("brand", "")
    name = record.get("product_name", "")
    count = len(verified)
    return (
        f"{brand} {name} — Elthio verified dietary supplement. "
        f"Verification status: {status}. "
        f"{count} ingredients confirmed against NIH DSLD official filing. "
        f"DSLD ID: {record.get('dsld_id', 'N/A')}."
    )


def _build_additional_properties(record: dict, audit: list[dict]) -> list[dict]:
    props = [
        {
            "@type": "PropertyValue",
            "name": "Elthio Verification Status",
            "value": record.get("overall_status", "UNVERIFIED"),
        },
        {
            "@type": "PropertyValue",
            "name": "NIH DSLD ID",
            "value": record.get("dsld_id", "N/A"),
        },
        {
            "@type": "PropertyValue",
            "name": "Label Accuracy",
            "value": f"{_accuracy_pct(audit):.0f}%",
        },
    ]
    if record.get("upc"):
        props.append({
            "@type": "PropertyValue",
            "name": "UPC",
            "value": record["upc"],
        })
    return props


def _accuracy_pct(audit: list[dict]) -> float:
    if not audit:
        return 0.0
    matched = sum(1 for e in audit if e.get("status") == "MATCH")
    return matched / len(audit) * 100


# ---------------------------------------------------------------------------
# HTML output — embeds JSON-LD for Google indexing
# ---------------------------------------------------------------------------

def generate_html_page(record: dict, jsonld: dict) -> str:
    """Generate a publishable HTML product page with embedded Schema.org markup."""
    status = record.get("overall_status", "UNVERIFIED")
    brand = record.get("brand", "Unknown")
    name = record.get("product_name", "Unknown")
    audit = record.get("audit", [])
    accuracy = _accuracy_pct(audit)
    summary = _build_audit_summary(audit)
    record_hash = _hash_record(record)

    status_color = {
        "VERIFIED":   "#2D6A4F",
        "INCOMPLETE": "#B5560A",
        "MISMATCH":   "#C1292E",
        "UNCERTAIN":  "#1B4F72",
        "UNVERIFIED": "#666",
    }.get(status, "#666")

    status_icon = {
        "VERIFIED":   "✅",
        "INCOMPLETE": "⚠️",
        "MISMATCH":   "❌",
        "UNCERTAIN":  "❓",
        "UNVERIFIED": "🔲",
    }.get(status, "?")

    ingredients_rows = ""
    for entry in audit:
        s = entry.get("status", "")
        icon = {"MATCH":"✅","MISMATCH":"❌","MISSING_NIH":"⚠️","MISSING_RETAIL":"🔍","UNCERTAIN":"❓"}.get(s,"?")
        retail = f"{entry.get('retail_amount','')} {entry.get('retail_unit','') or ''}".strip() or "—"
        nih    = f"{entry.get('nih_amount','')} {entry.get('nih_unit','') or ''}".strip() or "—"
        ingredients_rows += f"""
        <tr>
          <td>{icon}</td>
          <td>{entry.get('name','')}</td>
          <td>{retail}</td>
          <td>{nih}</td>
          <td style="font-size:11px;color:#888">{entry.get('diff','')[:60]}</td>
        </tr>"""

    now = datetime.now(timezone.utc).strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{brand} {name} — Elthio Verified | Elthio</title>
  <meta name="description" content="{brand} {name} supplement verified against NIH DSLD. Status: {status}. {len(audit)} ingredients audited.">

  <!-- Canonical Schema.org JSON-LD for search engines -->
  <script type="application/ld+json">
{json.dumps(jsonld, indent=2)}
  </script>

  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 32px 20px; background: #F7F5F0; color: #1A1814; }}
    .header {{ background: #1A1814; color: #F7F5F0; padding: 32px; border-radius: 8px; margin-bottom: 24px; }}
    .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .header .brand {{ font-size: 13px; color: #9B9488; margin-bottom: 16px; }}
    .badge {{ display: inline-block; background: {status_color}; color: white; padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
    .stat {{ background: white; border: 1px solid #E2DDD4; border-radius: 8px; padding: 16px; text-align: center; }}
    .stat .val {{ font-size: 28px; font-weight: 800; display: block; }}
    .stat .lbl {{ font-size: 10px; color: #9B9488; letter-spacing: 0.1em; }}
    .card {{ background: white; border: 1px solid #E2DDD4; border-radius: 8px; padding: 24px; margin-bottom: 16px; }}
    .card h2 {{ font-size: 14px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th {{ text-align: left; color: #9B9488; font-size: 10px; letter-spacing: 0.1em; padding: 8px; border-bottom: 2px solid #E2DDD4; font-weight: 400; }}
    td {{ padding: 8px; border-bottom: 1px solid #F0EDE6; }}
    .hash {{ font-family: monospace; font-size: 10px; color: #9B9488; word-break: break-all; }}
    .footer {{ font-size: 11px; color: #9B9488; text-align: center; margin-top: 32px; line-height: 1.8; }}
    @media (max-width: 600px) {{ .stats {{ grid-template-columns: repeat(2,1fr); }} }}
  </style>
</head>
<body>

<div class="header">
  <div class="brand">ELTHIO · VERIFIED SUPPLEMENT RECORD</div>
  <h1>{brand} — {name}</h1>
  <span class="badge">{status_icon} {status}</span>
</div>

<div class="stats">
  <div class="stat">
    <span class="val" style="color:#2D6A4F">{accuracy:.0f}%</span>
    <span class="lbl">LABEL ACCURACY</span>
  </div>
  <div class="stat">
    <span class="val">{summary['MATCH']}</span>
    <span class="lbl">VERIFIED</span>
  </div>
  <div class="stat">
    <span class="val" style="color:{'#C1292E' if summary['MISMATCH'] else '#2D6A4F'}">{summary['MISMATCH']}</span>
    <span class="lbl">MISMATCHES</span>
  </div>
  <div class="stat">
    <span class="val">{len(audit)}</span>
    <span class="lbl">TOTAL INGREDIENTS</span>
  </div>
</div>

<div class="card">
  <h2>📋 Product Details</h2>
  <table>
    <tr><td style="color:#9B9488;width:160px">Brand</td><td>{brand}</td></tr>
    <tr><td style="color:#9B9488">Product</td><td>{name}</td></tr>
    <tr><td style="color:#9B9488">UPC</td><td>{record.get('upc') or 'N/A'}</td></tr>
    <tr><td style="color:#9B9488">NIH DSLD ID</td><td>{record.get('dsld_id', 'N/A')}</td></tr>
    <tr><td style="color:#9B9488">Verified</td><td>{now}</td></tr>
    <tr><td style="color:#9B9488">Source URL</td><td><a href="{record.get('source_url','')}" style="color:#1B4F72">{record.get('source_url','N/A')}</a></td></tr>
  </table>
</div>

<div class="card">
  <h2>🧪 Ingredient Audit</h2>
  <table>
    <thead>
      <tr>
        <th></th>
        <th>INGREDIENT</th>
        <th>RETAIL LABEL</th>
        <th>NIH VERIFIED</th>
        <th>NOTES</th>
      </tr>
    </thead>
    <tbody>{ingredients_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>🔐 Verification Proof</h2>
  <p style="font-size:12px;color:#9B9488;margin-bottom:12px;line-height:1.6">
    This record's integrity can be independently verified using the SHA-256 hash below.
    The hash is derived from the canonical ingredient data and NIH DSLD anchor.
  </p>
  <div class="hash">{record_hash}</div>
</div>

<div class="footer">
  <p>Generated by <strong>Elthio</strong> · elthio.health</p>
  <p>Verified against NIH Dietary Supplement Label Database (DSLD)</p>
  <p style="margin-top:8px;font-size:10px">
    This verification confirms label data consistency — not product safety or efficacy.
    Not medical advice. Consult a healthcare professional before taking supplements.
  </p>
</div>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Batch feed generator
# ---------------------------------------------------------------------------

def generate_feed(records: list[dict]) -> dict:
    """
    Generate a JSON feed of multiple verified records.
    Suitable for API responses and data licensing.
    """
    return {
        "@context": ELTHIO_CONTEXT,
        "@type": "elthio:VerifiedFeed",
        "elthio:version": ELTHIO_SCHEMA_VERSION,
        "elthio:generatedAt": datetime.now(timezone.utc).isoformat(),
        "elthio:totalRecords": len(records),
        "elthio:records": [golden_record_to_jsonld(r) for r in records],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Elthio Schema Generator")
    parser.add_argument("input", help="Path to golden_record.json or folder for batch mode")
    parser.add_argument("--html", action="store_true", help="Generate HTML product page")
    parser.add_argument("--feed", action="store_true", help="Batch mode — process all JSON files in folder")
    parser.add_argument("--out", help="Output file path (default: auto-named)")
    args = parser.parse_args()

    if args.feed:
        # Batch mode
        folder = Path(args.input)
        records = []
        for f in folder.glob("*.json"):
            try:
                records.append(json.loads(f.read_text(encoding="utf-8")))
                print(f"  Loaded: {f.name}")
            except Exception as e:
                print(f"  Skipped {f.name}: {e}")

        feed = generate_feed(records)
        out = Path(args.out or "elthio_feed.json")
        out.write_text(json.dumps(feed, indent=2), encoding="utf-8")
        print(f"\n✅ Feed generated: {out} ({len(records)} records)")

    else:
        # Single record mode
        record = json.loads(Path(args.input).read_text(encoding="utf-8"))
        jsonld = golden_record_to_jsonld(record)

        if args.html:
            html = generate_html_page(record, jsonld)
            product_slug = f"{record.get('brand','unknown')}_{record.get('product_name','unknown')}".lower()
            product_slug = "".join(c if c.isalnum() else "_" for c in product_slug)[:60]
            out = Path(args.out or f"elthio_{product_slug}.html")
            out.write_text(html, encoding="utf-8")
            print(f"\n✅ HTML page saved: {out}")
            print(f"   Open in browser or publish to elthio.health")
        else:
            out = Path(args.out or "elthio_schema.jsonld")
            out.write_text(json.dumps(jsonld, indent=2), encoding="utf-8")
            print(f"\n✅ JSON-LD saved: {out}")

        # Always print summary
        audit = record.get("audit", [])
        print(f"\n   Product  : {record.get('brand')} — {record.get('product_name')}")
        print(f"   Status   : {record.get('overall_status')}")
        print(f"   Accuracy : {_accuracy_pct(audit):.0f}%")
        print(f"   Hash     : {_hash_record(record)[:16]}...")
        print(f"   DSLD ID  : {record.get('dsld_id')}")