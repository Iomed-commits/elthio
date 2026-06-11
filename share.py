"""
share.py — Shareable stack URLs for Elthio

Creates public shareable URLs for supplement stacks.
elthio.health/stack/abc123 → shows stack, Safety Score, interactions.

No auth required to view. Optional email to track your shares.
Slugs are 8-char random strings — short enough to share,
unique enough to not collide.
"""
from __future__ import annotations

import json
import logging
import os
import random
import string
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

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
)
SITE_URL     = os.environ.get("SITE_URL", "https://elthio.health")


# ── Supabase helpers ──────────────────────────────────────────────────────────
def _sh() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _supa_post(table: str, body: dict) -> Any:
    url  = f"{SUPABASE_URL}/rest/v1/{table}"
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data, headers=_sh(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _supa_get(table: str, params: dict) -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_sh())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()) or []


def _supa_rpc(fn: str, params: dict) -> Any:
    url  = f"{SUPABASE_URL}/rest/v1/rpc/{fn}"
    data = json.dumps(params).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={**_sh(), "Prefer": ""},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


# ── Slug generator ────────────────────────────────────────────────────────────
def generate_slug(length: int = 8) -> str:
    """Generate a short random slug — e.g. 'k3mX9pQr'"""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def unique_slug() -> str:
    """Generate a slug that doesn't already exist in the database."""
    for _ in range(10):
        slug = generate_slug()
        existing = _supa_get(
            "shared_stacks",
            {"slug": f"eq.{slug}", "select": "slug", "limit": "1"},
        )
        if not existing:
            return slug
    return generate_slug(12)


# ── Create share ──────────────────────────────────────────────────────────────
def create_share(
    medications:  list[str],
    supplements:  list[str],
    interactions: list[dict],
    synergies:    list[dict],
    near_misses:  list[dict],
    safety_score: int | None = None,
    safety_band:  str | None = None,
    email:        str = "",
    title:        str = "My Supplement Stack",
    note:         str = "",
) -> dict:
    """
    Create a shareable stack URL.
    Returns { slug, url, share_url, expires_at }
    """
    slug = unique_slug()

    safe_interactions = [
        {
            "title":       ix.get("title", ""),
            "severity":    ix.get("severity", ""),
            "detail":      ix.get("detail", "")[:200] if ix.get("detail") else "",
            "instruction": ix.get("instruction", "")[:200] if ix.get("instruction") else "",
            "source":      ix.get("source", ""),
            "evidence":    ix.get("evidence", ""),
        }
        for ix in (interactions or [])[:10]
    ]

    safe_synergies = [
        {
            "title":        s.get("title", ""),
            "supplement_a": s.get("supplement_a", ""),
            "supplement_b": s.get("supplement_b", ""),
            "detail":       s.get("detail", "")[:150] if s.get("detail") else "",
        }
        for s in (synergies or [])[:5]
    ]

    row = {
        "slug":         slug,
        "email":        email.lower().strip() if email else None,
        "medications":  medications,
        "supplements":  supplements,
        "safety_score": safety_score,
        "safety_band":  safety_band,
        "interactions": safe_interactions,
        "synergies":    safe_synergies,
        "near_misses":  [],
        "title":        title or "My Supplement Stack",
        "note":         note or "",
        "view_count":   0,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }

    inserted = _supa_post("shared_stacks", row)
    if isinstance(inserted, list) and inserted:
        expires_at = inserted[0].get("expires_at", "")
    else:
        expires_at = ""

    share_url = f"{SITE_URL}/stack/{slug}"

    log.info("Created share: %s → %s", slug, share_url)
    return {
        "slug":       slug,
        "url":        share_url,
        "share_url":  share_url,
        "expires_at": expires_at,
        "created":    True,
    }


# ── Get share ─────────────────────────────────────────────────────────────────
def get_share(slug: str) -> dict | None:
    """
    Retrieve a shared stack by slug.
    Increments view count.
    Returns the stack dict or None if not found / expired.
    """
    try:
        results = _supa_get(
            "shared_stacks",
            {"slug": f"eq.{slug}", "select": "*", "limit": "1"},
        )
        if not results:
            return None

        stack = results[0]

        expires_at = stack.get("expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                )
                if exp < datetime.now(timezone.utc):
                    log.info("Share %s has expired", slug)
                    return None
            except Exception:
                pass

        try:
            _supa_rpc("increment_view_count", {"stack_slug": slug})
        except Exception:
            pass

        return stack

    except Exception as e:
        log.warning("get_share error for %s: %s", slug, e)
        return None


# ── Get shares by email ───────────────────────────────────────────────────────
def get_my_shares(email: str) -> list[dict]:
    """Get all shares created by a user email."""
    if not email or "@" not in email:
        return []
    try:
        return _supa_get(
            "shared_stacks",
            {
                "email":  f"eq.{email.lower().strip()}",
                "order":  "created_at.desc",
                "limit":  "10",
                "select": "slug,title,safety_score,view_count,created_at",
            },
        )
    except Exception as e:
        log.warning("get_my_shares error: %s", e)
        return []


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("\n=== SHARE SELF TEST ===\n")

    print("[1] Create share")
    result = create_share(
        medications  = ["warfarin", "levothyroxine"],
        supplements  = ["vitamin d3", "magnesium", "fish oil", "coq10"],
        interactions = [
            {"title": "Warfarin + Vitamin K2", "severity": "critical",
             "detail": "Vitamin K directly opposes warfarin.",
             "instruction": "Monitor INR closely.",
             "source": "NIH ODS", "evidence": "strong"},
        ],
        synergies    = [
            {"title": "Vitamin D3 + K2 synergy",
             "supplement_a": "vitamin d3", "supplement_b": "vitamin k2",
             "detail": "K2 directs calcium to bones not arteries."},
        ],
        near_misses  = [],
        safety_score = 71,
        safety_band  = "Review needed",
        title        = "My Longevity Stack",
        note         = "Started this stack in January 2024",
    )
    print(f"  ✅ Created: {result['share_url']}")
    slug = result["slug"]

    print("\n[2] Get share")
    stack = get_share(slug)
    if stack:
        print(f"  ✅ Retrieved: {stack['title']}")
        print(f"     Medications: {stack['medications']}")
        print(f"     Safety Score: {stack['safety_score']}")
        print(f"     Interactions: {len(stack['interactions'])}")
        print(f"     View count: {stack['view_count']}")
    else:
        print("  ❌ Not found")

    print("\n=== TEST COMPLETE ===\n")
