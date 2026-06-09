"""
safety_score.py — Elthio Safety Score Engine

Calculates a 0-100 safety score for a user's supplement + medication stack.
Every deduction and bonus is traceable to real data from existing engines.

Score bands:
  90-100  Excellent  (green)
  75-89   Good       (yellow)
  50-74   Review needed (orange)
  0-49    Action required (red)
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

BASE_SCORE = 100

DEDUCTIONS = {
    "critical_interaction":     25,
    "high_interaction":         15,
    "moderate_interaction":      8,
    "informational_interaction": 2,
    "near_miss":                 3,
    "nih_mismatch":             10,
    "nih_unverified":            3,
    "duplicate_ingredient":      5,
    "timing_conflict":           5,
    "over_supplemented":         8,
    "timing_conflict_supp":      3,
}

BONUSES = {
    "all_nih_verified":       5,
    "zero_critical":          5,
    "reasonable_stack_size":  3,
    "has_timing_schedule":    2,
    "has_synergies":          3,
}

SCORE_BANDS = [
    (90, 100, "Excellent",       "#1D9E75", "🟢"),
    (75,  89, "Good",            "#EF9F27", "🟡"),
    (50,  74, "Review needed",   "#F97316", "🟠"),
    ( 0,  49, "Action required", "#E24B4A", "🔴"),
]


def get_band(score: int) -> dict:
    for low, high, label, color, emoji in SCORE_BANDS:
        if low <= score <= high:
            return {"label": label, "color": color, "emoji": emoji}
    return {"label": "Unknown", "color": "#6b7280", "emoji": "⚪"}


def calculate_safety_score(
    medications: list[str],
    supplements: list[str],
    interactions: list[dict],
    near_misses: list[dict] | None = None,
    nih_statuses: dict[str, str] | None = None,
    timing_conflicts: list[dict] | None = None,
    synergies: list[dict] | None = None,
) -> dict[str, Any]:
    """Calculate a Safety Score from Med Check output."""
    score     = BASE_SCORE
    breakdown: list[dict] = []

    severity_counts: dict[str, int] = {}
    for ix in interactions or []:
        sev = (ix.get("severity") or "informational").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    for sev, count in severity_counts.items():
        key    = f"{sev}_interaction"
        points = DEDUCTIONS.get(key, 2)
        total  = points * count
        score -= total
        breakdown.append({
            "reason":   f"{count} {sev} interaction{'s' if count > 1 else ''} found",
            "impact":   "negative",
            "points":   -total,
            "category": "interactions",
        })

    nm_count = len(near_misses or [])
    if nm_count > 0:
        total  = DEDUCTIONS["near_miss"] * nm_count
        score -= total
        breakdown.append({
            "reason":   f"{nm_count} near-match{'es' if nm_count > 1 else ''} detected",
            "impact":   "negative",
            "points":   -total,
            "category": "interactions",
        })

    if nih_statuses:
        mismatch_count   = sum(1 for s in nih_statuses.values() if s == "MISMATCH")
        unverified_count = sum(
            1 for s in nih_statuses.values()
            if s in ("UNVERIFIED", "NOT_FOUND", "ERROR")
        )

        if mismatch_count > 0:
            total  = DEDUCTIONS["nih_mismatch"] * mismatch_count
            score -= total
            breakdown.append({
                "reason":   (
                    f"{mismatch_count} product label{'s' if mismatch_count > 1 else ''} "
                    f"don't match NIH records"
                ),
                "impact":   "negative",
                "points":   -total,
                "category": "quality",
            })

        if unverified_count > 0:
            total  = DEDUCTIONS["nih_unverified"] * unverified_count
            score -= total
            breakdown.append({
                "reason":   (
                    f"{unverified_count} product{'s' if unverified_count > 1 else ''} "
                    f"not yet NIH verified"
                ),
                "impact":   "negative",
                "points":   -total,
                "category": "quality",
            })

        all_products = list(nih_statuses.values())
        all_verified = all(s == "VERIFIED" for s in all_products) if all_products else False
        if all_verified and len(all_products) >= 2:
            score += BONUSES["all_nih_verified"]
            breakdown.append({
                "reason":   "All products NIH verified",
                "impact":   "positive",
                "points":   +BONUSES["all_nih_verified"],
                "category": "quality",
            })

    total_items = len(medications or []) + len(supplements or [])
    if total_items > 10:
        score -= DEDUCTIONS["over_supplemented"]
        breakdown.append({
            "reason":   f"Large stack ({total_items} items) — harder to monitor interactions",
            "impact":   "negative",
            "points":   -DEDUCTIONS["over_supplemented"],
            "category": "stack",
        })
    elif 0 < total_items <= 8:
        score += BONUSES["reasonable_stack_size"]
        breakdown.append({
            "reason":   "Manageable stack size",
            "impact":   "positive",
            "points":   +BONUSES["reasonable_stack_size"],
            "category": "stack",
        })

    tc_count = len(timing_conflicts or [])
    if tc_count > 0:
        total  = DEDUCTIONS["timing_conflict_supp"] * min(tc_count, 3)
        score -= total
        breakdown.append({
            "reason":   (
                f"{tc_count} timing conflict{'s' if tc_count > 1 else ''} "
                f"(take separately)"
            ),
            "impact":   "negative",
            "points":   -total,
            "category": "timing",
        })

    if synergies:
        score += BONUSES["has_synergies"]
        breakdown.append({
            "reason":   (
                f"{len(synergies)} beneficial supplement combination"
                f"{'s' if len(synergies) > 1 else ''} in your stack"
            ),
            "impact":   "positive",
            "points":   +BONUSES["has_synergies"],
            "category": "synergies",
        })

    if severity_counts.get("critical", 0) == 0:
        score += BONUSES["zero_critical"]
        breakdown.append({
            "reason":   "No critical interactions",
            "impact":   "positive",
            "points":   +BONUSES["zero_critical"],
            "category": "interactions",
        })

    score = max(0, min(100, score))
    band  = get_band(score)

    if score >= 90:
        summary = "Your stack looks safe — no significant interactions detected."
    elif score >= 75:
        summary = "Your stack is generally safe with a few things to be aware of."
    elif score >= 50:
        summary = "Your stack needs attention — review the interactions below."
    else:
        summary = "Your stack has serious safety concerns — please review with your pharmacist."

    return {
        "score":     score,
        "band":      band,
        "breakdown": breakdown,
        "summary":   summary,
        "inputs": {
            "medications":  len(medications or []),
            "supplements":  len(supplements or []),
            "interactions": len(interactions or []),
            "near_misses":  len(near_misses or []),
        },
    }


def score_from_med_check_result(
    medications: list[str],
    supplements: list[str],
    med_check_result: dict,
) -> dict[str, Any]:
    """Convenience wrapper — takes run_med_check() output."""
    return calculate_safety_score(
        medications  = medications,
        supplements  = supplements,
        interactions = med_check_result.get("interactions", []),
        near_misses  = med_check_result.get("near_misses", []),
        timing_conflicts = med_check_result.get("timing_conflicts", []),
        synergies    = med_check_result.get("synergies", []),
    )


def _supabase_rest() -> tuple[str, str]:
    url = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
    key = (
        os.environ.get("SUPABASE_KEY", "")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()
    return url, key


def save_score_to_supabase(
    email: str,
    score: int,
    band_label: str,
    medications: list[str],
    supplements: list[str],
) -> bool:
    """Save a score snapshot to Supabase safety_scores table."""
    base, key = _supabase_rest()
    if not base or not key:
        return False

    try:
        body = json.dumps({
            "email":       email.lower().strip(),
            "score":       score,
            "band":        band_label,
            "medications": medications,
            "supplements": supplements,
            "checked_at":  datetime.now(timezone.utc).isoformat(),
        }).encode()

        req = urllib.request.Request(
            f"{base.rstrip('/')}/rest/v1/safety_scores",
            data=body,
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        log.warning("save_score error: %s", e)
        return False


def get_score_history(email: str, limit: int = 30) -> list[dict]:
    """Get score history for trend display."""
    base, key = _supabase_rest()
    if not base or not key:
        return []

    try:
        params = urllib.parse.urlencode({
            "email":  f"eq.{email.lower().strip()}",
            "order":  "checked_at.desc",
            "limit":  str(limit),
            "select": "score,band,checked_at",
        })
        req = urllib.request.Request(
            f"{base.rstrip('/')}/rest/v1/safety_scores?{params}",
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()) or []
    except Exception as e:
        log.warning("get_score_history error: %s", e)
        return []


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("\n=== SAFETY SCORE SELF TEST ===\n")

    result1 = calculate_safety_score(
        medications  = ["levothyroxine"],
        supplements  = ["vitamin d3", "magnesium"],
        interactions = [],
        near_misses  = [],
    )
    print(f"[1] Clean stack: {result1['score']}/100 {result1['band']['emoji']} "
          f"{result1['band']['label']}")
    print(f"    {result1['summary']}")

    result2 = calculate_safety_score(
        medications  = ["warfarin"],
        supplements  = ["vitamin k2", "fish oil", "coq10"],
        interactions = [
            {"severity": "critical", "title": "Warfarin + Vitamin K2"},
            {"severity": "moderate", "title": "Warfarin + Fish Oil"},
        ],
        near_misses  = [{"title": "CoQ10 near-miss"}],
    )
    print(f"\n[2] Critical interaction: {result2['score']}/100 "
          f"{result2['band']['emoji']} {result2['band']['label']}")
    print(f"    {result2['summary']}")
    for b in result2["breakdown"]:
        sign = "+" if b["impact"] == "positive" else ""
        print(f"    {sign}{b['points']}  {b['reason']}")

    result3 = calculate_safety_score(
        medications  = ["warfarin", "metformin", "atorvastatin", "lisinopril"],
        supplements  = ["coq10", "magnesium", "vitamin d3", "omega-3",
                        "vitamin k2", "nac", "berberine", "ashwagandha"],
        interactions = [{"severity": "critical", "title": "Warfarin + Vitamin K2"}],
        near_misses  = [],
    )
    print(f"\n[3] Large stack with critical: {result3['score']}/100 "
          f"{result3['band']['emoji']} {result3['band']['label']}")

    print("\n=== ALL TESTS COMPLETE ===\n")
