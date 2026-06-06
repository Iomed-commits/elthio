"""
weekly_digest.py — Send weekly stack check digest to all saved users.
Run via Railway cron: 0 9 * * 1  (every Monday 9am UTC)
Or manually: python weekly_digest.py
"""
from __future__ import annotations
import json
import logging
import os
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from supabase_client import normalize_supabase_url

SUPABASE_URL = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY", "")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
).strip()


def get_all_stacks() -> list[dict]:
    """Fetch all saved stacks from Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/saved_stacks?select=*&limit=1000"
    req = urllib.request.Request(url, headers={
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()) or []


def run_weekly_digest():
    from med_check_engine import run_med_check
    from stack_save import (
        send_digest_email, record_check,
        detect_severity_change,
    )

    stacks = get_all_stacks()
    log.info("Running weekly digest for %d saved stacks", len(stacks))

    sent = skipped = errors = 0

    for stack in stacks:
        email = stack.get("email", "")
        meds  = stack.get("medications", [])
        supps = stack.get("supplements", [])

        if not email or (not meds and not supps):
            skipped += 1
            continue

        try:
            result          = run_med_check(meds, supps, [])
            interactions    = result.get("interactions", [])
            record_check(email, meds, supps, interactions)
            severity_change = detect_severity_change(email)

            ok = send_digest_email(
                email, meds, supps, interactions, severity_change
            )
            if ok:
                sent += 1
                log.info("Digest sent: %s (%d interactions)", email, len(interactions))
            else:
                errors += 1
        except Exception as e:
            log.error("Digest failed for %s: %s", email, e)
            errors += 1

    log.info("Weekly digest complete: %d sent, %d skipped, %d errors",
             sent, skipped, errors)
    return {"sent": sent, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    result = run_weekly_digest()
    print(f"\nDone: {result}")
