"""
memory.py — Conversation memory for returning Elthio users

Stores Med Check results per user session.
Retrieves past sessions to give Claude context about the user's history.
Enables: "Last time you checked, warfarin + K2 was flagged — still taking both?"
"""
from __future__ import annotations

import json
import logging
import os
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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"


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


def _supa_patch(table: str, params: dict, body: dict) -> None:
    url  = f"{SUPABASE_URL}/rest/v1/{table}?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={**_sh(), "Prefer": ""},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10)


# ── Save session ──────────────────────────────────────────────────────────────
def save_session(
    email: str,
    medications: list[str],
    supplements: list[str],
    med_check_result: dict,
    safety_score: int | None = None,
) -> bool:
    """
    Save a Med Check session to conversation_memory.
    Called after every Med Check run for users with a saved email.
    """
    if not email or "@" not in email:
        return False

    email = email.lower().strip()

    interactions = med_check_result.get("interactions", [])
    synergies    = med_check_result.get("synergies",    [])

    severity_counts = {}
    for ix in interactions:
        sev = (ix.get("severity") or "informational").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    top_interactions = [
        {
            "title":    ix.get("title", ""),
            "severity": ix.get("severity", ""),
            "drug":     ix.get("drug", ix.get("supplement_a", "")),
            "supp":     ix.get("supplement", ix.get("supplement_b", "")),
        }
        for ix in interactions[:3]
    ]

    top_synergies = [
        {
            "title":  s.get("title", ""),
            "supp_a": s.get("supplement_a", ""),
            "supp_b": s.get("supplement_b", ""),
        }
        for s in synergies[:3]
    ]

    summary = _build_summary(
        medications, supplements,
        severity_counts, top_interactions, safety_score
    )

    try:
        _supa_post("conversation_memory", {
            "email":            email,
            "session_date":     datetime.now(timezone.utc).isoformat(),
            "medications":      medications,
            "supplements":      supplements,
            "safety_score":     safety_score,
            "critical_count":   severity_counts.get("critical",      0),
            "high_count":       severity_counts.get("high",          0),
            "moderate_count":   severity_counts.get("moderate",      0),
            "top_interactions": top_interactions,
            "synergies_found":  top_synergies,
            "resolved_flags":   [],
            "summary":          summary,
        })
        log.info("Session saved for %s", email)
        return True
    except Exception as e:
        log.warning("save_session error: %s", e)
        return False


def _build_summary(
    medications: list[str],
    supplements: list[str],
    severity_counts: dict,
    top_interactions: list[dict],
    safety_score: int | None,
) -> str:
    """Build a plain English summary for Claude to reference."""
    parts = []

    if medications:
        parts.append(f"Medications: {', '.join(medications)}")
    if supplements:
        parts.append(f"Supplements: {', '.join(supplements)}")
    if safety_score is not None:
        parts.append(f"Safety Score: {safety_score}/100")

    critical = severity_counts.get("critical", 0)
    high     = severity_counts.get("high",     0)
    moderate = severity_counts.get("moderate", 0)

    if critical > 0:
        parts.append(f"{critical} critical interaction(s) flagged")
    if high > 0:
        parts.append(f"{high} high interaction(s) flagged")
    if moderate > 0:
        parts.append(f"{moderate} moderate interaction(s) flagged")
    if not (critical + high + moderate):
        parts.append("No significant interactions found")

    for ix in top_interactions[:2]:
        if ix.get("title"):
            parts.append(f"Flagged: {ix['title']} ({ix.get('severity', '')})")

    return ". ".join(parts)


# ── Get memory ────────────────────────────────────────────────────────────────
def get_memory(email: str, limit: int = 5) -> list[dict]:
    """
    Get past Med Check sessions for a user.
    Returns most recent sessions first.
    """
    if not email or "@" not in email:
        return []
    try:
        return _supa_get("conversation_memory", {
            "email":  f"eq.{email.lower().strip()}",
            "order":  "session_date.desc",
            "limit":  str(limit),
            "select": "*",
        })
    except Exception as e:
        log.warning("get_memory error: %s", e)
        return []


def get_last_session(email: str) -> dict | None:
    """Get the most recent session for a user."""
    sessions = get_memory(email, limit=1)
    return sessions[0] if sessions else None


# ── Build Claude context from memory ─────────────────────────────────────────
def build_memory_context(email: str) -> str:
    """
    Build a context string for Claude based on the user's history.
    This gets prepended to the AI Med Check prompt so Claude
    can reference past sessions naturally.
    """
    sessions = get_memory(email, limit=3)
    if not sessions:
        return ""

    last  = sessions[0]
    parts = []

    try:
        last_date = datetime.fromisoformat(
            last["session_date"].replace("Z", "+00:00")
        )
        now       = datetime.now(timezone.utc)
        days_ago  = (now - last_date).days
        if days_ago == 0:
            when = "earlier today"
        elif days_ago == 1:
            when = "yesterday"
        elif days_ago < 7:
            when = f"{days_ago} days ago"
        elif days_ago < 30:
            weeks = days_ago // 7
            when  = f"{weeks} week{'s' if weeks > 1 else ''} ago"
        else:
            months = days_ago // 30
            when   = f"{months} month{'s' if months > 1 else ''} ago"
    except Exception:
        when = "previously"

    parts.append(f"USER HISTORY ({len(sessions)} past session{'s' if len(sessions) > 1 else ''}):")
    parts.append(f"Last check: {when}")

    if last.get("summary"):
        parts.append(f"Last session summary: {last['summary']}")

    critical_count = last.get("critical_count", 0)
    high_count     = last.get("high_count",     0)
    if critical_count > 0:
        parts.append(
            f"IMPORTANT: Last time, {critical_count} critical "
            f"interaction(s) were flagged — ask if they have been resolved."
        )
    elif high_count > 0:
        parts.append(
            f"Note: Last time, {high_count} high-severity "
            f"interaction(s) were flagged."
        )

    return "\n".join(parts)


def detect_stack_changes(
    email: str,
    current_meds: list[str],
    current_supps: list[str],
) -> dict:
    """
    Compare current stack to last session.
    Returns { added_meds, removed_meds, added_supps, removed_supps }
    """
    last = get_last_session(email)
    if not last:
        return {}

    last_meds  = set(m.lower() for m in last.get("medications", []))
    last_supps = set(s.lower() for s in last.get("supplements", []))
    curr_meds  = set(m.lower() for m in current_meds)
    curr_supps = set(s.lower() for s in current_supps)

    return {
        "added_meds":    list(curr_meds  - last_meds),
        "removed_meds":  list(last_meds  - curr_meds),
        "added_supps":   list(curr_supps - last_supps),
        "removed_supps": list(last_supps - curr_supps),
        "has_changes":   bool(
            (curr_meds | curr_supps) != (last_meds | last_supps)
        ),
    }


# ── Mark resolved ─────────────────────────────────────────────────────────────
def mark_resolved(email: str, interaction_title: str) -> bool:
    """
    Mark an interaction as resolved — user confirmed they stopped
    taking one of the substances or got medical clearance.
    """
    try:
        sessions = get_memory(email, limit=1)
        if not sessions:
            return False
        session    = sessions[0]
        session_id = session["id"]
        resolved   = session.get("resolved_flags", [])
        resolved.append({
            "title":       interaction_title,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
        _supa_patch(
            "conversation_memory",
            {"id": f"eq.{session_id}"},
            {"resolved_flags": resolved},
        )
        return True
    except Exception as e:
        log.warning("mark_resolved error: %s", e)
        return False


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("\n=== MEMORY SELF TEST ===\n")

    test_email = "test@elthio.health"

    print("[1] Save session")
    ok = save_session(
        email       = test_email,
        medications = ["warfarin", "levothyroxine"],
        supplements = ["vitamin k2", "magnesium", "fish oil"],
        med_check_result = {
            "interactions": [
                {"title": "Warfarin + Vitamin K2", "severity": "critical",
                 "drug": "warfarin", "supplement": "vitamin k2"},
                {"title": "Levothyroxine + Magnesium", "severity": "moderate",
                 "drug": "levothyroxine", "supplement": "magnesium"},
            ],
            "synergies": [
                {"title": "Magnesium + Vitamin D3 synergy",
                 "supplement_a": "magnesium", "supplement_b": "vitamin d3"},
            ],
        },
        safety_score = 62,
    )
    print(f"  {'✅ Saved' if ok else '❌ Failed'}")

    print("\n[2] Get memory")
    sessions = get_memory(test_email)
    print(f"  ✅ {len(sessions)} session(s) found")
    if sessions:
        print(f"     Summary: {sessions[0].get('summary', '')[:80]}")

    print("\n[3] Build Claude context")
    ctx = build_memory_context(test_email)
    print(f"  ✅ Context ({len(ctx)} chars):")
    for line in ctx.split("\n"):
        print(f"     {line}")

    print("\n[4] Detect stack changes")
    changes = detect_stack_changes(
        test_email,
        current_meds  = ["warfarin", "levothyroxine", "metformin"],
        current_supps = ["vitamin k2", "magnesium"],
    )
    print(f"  ✅ Added meds:    {changes.get('added_meds', [])}")
    print(f"     Removed supps: {changes.get('removed_supps', [])}")

    print("\n=== TEST COMPLETE ===\n")
