"""
pharmacy_history.py — Manual pharmacy history entry and parsing

Users paste their pharmacy printout or EOB (Explanation of Benefits)
text and Claude extracts their medication list automatically.
Saves to Supabase pharmacy_history table.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from supabase_client import normalize_supabase_url

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL      = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY      = (
    os.environ.get("SUPABASE_KEY", "")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
).strip()
CLAUDE_MODEL      = "claude-sonnet-4-5-20250929"


def _parse_claude_json(raw: str) -> dict:
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end   = raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def parse_pharmacy_text(text: str) -> dict:
    """
    Use Claude to extract medications from pasted pharmacy text.
    Returns {medications: [...], raw_count: int, confidence: str}
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    system = """You are a pharmacy text parser for a supplement safety app.
Extract medication names from pasted pharmacy printouts, EOB statements,
discharge summaries, or any medical text.

Return ONLY valid JSON — no markdown, no explanation:
{
  "medications": [
    {
      "name": "generic drug name",
      "brand_name": "brand name if shown",
      "dose": "10mg",
      "frequency": "once daily",
      "prescriber": "Dr. Smith if shown",
      "fill_date": "2024-01-15 if shown",
      "days_supply": 30,
      "condition": "condition being treated if mentioned"
    }
  ],
  "confidence": "high|medium|low",
  "notes": "any relevant context"
}

Rules:
- Extract ALL medications mentioned, including OTC drugs
- Use generic names (not brand names) in the name field
- dose: include units (mg, mcg, IU)
- frequency: once daily, twice daily, as needed, etc.
- If a field is not mentioned, use null
- Ignore supplements — only extract prescription and OTC medications
- confidence high = clear medication list, medium = some ambiguity, low = unclear text"""

    body = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 2000,
        "system":     system,
        "messages":   [{"role": "user",
                        "content": f"Extract medications from this text:\n\n{text[:6000]}"}],
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

    parsed = _parse_claude_json(resp["content"][0]["text"])

    return {
        "medications": parsed.get("medications", []),
        "raw_count":   len(parsed.get("medications", [])),
        "confidence":  parsed.get("confidence", "medium"),
        "notes":       parsed.get("notes", ""),
    }


def save_pharmacy_history(email: str, medications: list[dict]) -> bool:
    """Save parsed pharmacy history to Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("save_pharmacy_history: Supabase not configured")
        return False
    try:
        url  = f"{SUPABASE_URL.rstrip('/')}/rest/v1/pharmacy_history"
        body = json.dumps({
            "email":       email.lower().strip(),
            "medications": medications,
            "parsed_at":   datetime.now(timezone.utc).isoformat(),
        }).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        log.error("save_pharmacy_history error: %s", e)
        return False


if __name__ == "__main__":
    sample = """
    PHARMACY RECEIPT
    Patient: John Doe    Date: 01/15/2024

    1. Warfarin Sodium 5mg Tablets
       Qty: 30  Days Supply: 30  Dr. Smith
       Take 1 tablet daily as directed

    2. Metformin HCl 500mg Tablets
       Qty: 60  Days Supply: 30  Dr. Johnson
       Take 1 tablet twice daily with meals

    3. Atorvastatin Calcium 20mg
       Qty: 30  Days Supply: 30  Dr. Smith
       Take 1 tablet at bedtime

    4. Lisinopril 10mg
       Qty: 30  Days Supply: 30  Dr. Johnson
       Take 1 tablet daily
    """

    print("\n=== PHARMACY PARSER SELF TEST ===\n")
    result = parse_pharmacy_text(sample)
    print(f"Extracted {result['raw_count']} medications:")
    for med in result["medications"]:
        print(f"  - {med['name']} {med.get('dose', '')} "
              f"({med.get('frequency', '')})")
    print(f"Confidence: {result['confidence']}")
