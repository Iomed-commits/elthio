"""
stack_save.py — Save/load user stacks and send weekly digest emails.
Uses Supabase for storage and SendGrid for email delivery.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
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
).strip()
SENDGRID_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL   = os.environ.get("FROM_EMAIL", "hello@elthio.health")
SITE_URL     = os.environ.get("SITE_URL", "https://elthio.health")


def _rest_base() -> str:
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL must be set")
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1"


def _supa_headers() -> dict:
    if not SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY must be set")
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _supa_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
) -> Any:
    url = f"{_rest_base()}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data, headers=_supa_headers(), method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")[:400]
        raise ValueError(f"Supabase {method} {path} failed ({e.code}): {err}") from e


# ── Stack save / load ─────────────────────────────────────────────────────────

def save_stack(
    email: str,
    medications: list[str],
    supplements: list[str],
) -> dict:
    """
    Upsert a user's stack by email.
    Returns the saved record.
    """
    email = email.lower().strip()
    if not email or "@" not in email:
        raise ValueError("Valid email required")

    payload = {
        "email":       email,
        "medications": medications,
        "supplements": supplements,
        "updated_at":  datetime.now(timezone.utc).isoformat(),
    }

    existing = get_stack(email)
    if existing:
        result = _supa_request(
            "PATCH",
            "saved_stacks",
            body=payload,
            params={"email": f"eq.{email}"},
        )
        log.info("Stack updated for %s", email)
    else:
        result = _supa_request("POST", "saved_stacks", body=payload)
        log.info("Stack created for %s", email)

    return result[0] if isinstance(result, list) and result else payload


def get_stack(email: str) -> dict | None:
    """Load a saved stack by email. Returns None if not found."""
    email = email.lower().strip()
    try:
        results = _supa_request(
            "GET",
            "saved_stacks",
            params={"email": f"eq.{email}", "limit": "1"},
        )
        return results[0] if results else None
    except Exception as e:
        log.warning("get_stack error: %s", e)
        return None


def record_check(
    email: str,
    medications: list[str],
    supplements: list[str],
    interactions: list[dict],
) -> None:
    """
    Record a Med Check run to stack_checks history table.
    Used to detect severity changes over time.
    """
    email = email.lower().strip()

    severity_counts: dict[str, int] = {}
    interaction_ids: list[str] = []
    for ix in interactions:
        sev = ix.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if ix.get("id"):
            interaction_ids.append(str(ix["id"]))

    try:
        _supa_request("POST", "stack_checks", body={
            "email":           email,
            "medications":     medications,
            "supplements":     supplements,
            "interaction_ids": interaction_ids,
            "severity_counts": severity_counts,
            "checked_at":      datetime.now(timezone.utc).isoformat(),
        })
        existing = get_stack(email) or {}
        count = int(existing.get("check_count") or 0) + 1
        _supa_request("PATCH", "saved_stacks", body={
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "check_count":  count,
        }, params={"email": f"eq.{email}"})
    except Exception as e:
        log.warning("record_check error: %s", e)


def get_check_history(email: str, limit: int = 10) -> list[dict]:
    """Get past Med Check results for a user."""
    email = email.lower().strip()
    try:
        return _supa_request(
            "GET",
            "stack_checks",
            params={
                "email": f"eq.{email}",
                "order": "checked_at.desc",
                "limit": str(limit),
            },
        ) or []
    except Exception as e:
        log.warning("get_check_history error: %s", e)
        return []


def detect_severity_change(email: str) -> dict | None:
    """
    Compare the last two checks. Returns change info if severity worsened.
    Returns None if no change or not enough history.
    """
    history = get_check_history(email, limit=2)
    if len(history) < 2:
        return None

    latest = history[0].get("severity_counts", {})
    prev   = history[1].get("severity_counts", {})

    severity_order = ["critical", "high", "moderate", "informational"]
    for sev in severity_order:
        if latest.get(sev, 0) > prev.get(sev, 0):
            return {
                "changed": True,
                "severity": sev,
                "was":      prev.get(sev, 0),
                "now":      latest.get(sev, 0),
                "message":  f"New {sev} interaction detected since last check",
            }
    return None


# ── Email digest ──────────────────────────────────────────────────────────────

def send_digest_email(
    email: str,
    medications: list[str],
    supplements: list[str],
    interactions: list[dict],
    severity_change: dict | None = None,
) -> bool:
    """
    Send weekly digest email via SendGrid.
    Returns True on success.
    """
    if not SENDGRID_KEY:
        log.warning("SENDGRID_API_KEY not set — skipping email")
        return False

    subject, body_html = _build_email(
        email, medications, supplements, interactions, severity_change
    )

    payload = json.dumps({
        "personalizations": [{"to": [{"email": email}]}],
        "from":             {"email": FROM_EMAIL, "name": "Elthio"},
        "subject":          subject,
        "content":          [{"type": "text/html", "value": body_html}],
    }).encode()

    try:
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {SENDGRID_KEY}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            log.info("Digest sent to %s — status %d", email, r.status)
            return r.status in (200, 202)
    except Exception as e:
        log.error("SendGrid error for %s: %s", email, e)
        return False


def _build_email(
    email: str,
    medications: list[str],
    supplements: list[str],
    interactions: list[dict],
    severity_change: dict | None,
) -> tuple[str, str]:
    """Build subject line and HTML body for the digest email."""

    has_critical = any(
        i.get("severity") in ("critical", "high") for i in interactions
    )
    change_alert = severity_change and severity_change.get("changed")

    if change_alert:
        subject = f"⚠️ New {severity_change['severity']} interaction in your stack — Elthio"
    elif has_critical:
        subject = "⚠️ Your weekly Elthio stack check — action needed"
    else:
        subject = "✅ Your weekly Elthio stack check — all clear"

    sev_color = {
        "critical":      "#dc2626",
        "high":          "#d97706",
        "moderate":      "#2563eb",
        "informational": "#6b7280",
    }

    ix_rows = ""
    if interactions:
        for ix in interactions[:5]:
            sev   = ix.get("severity", "informational")
            color = sev_color.get(sev, "#6b7280")
            ix_rows += f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6">
                <span style="color:{color};font-weight:600;font-size:12px;text-transform:uppercase">
                  {sev}
                </span><br>
                <span style="font-size:14px;color:#111827">{ix.get('title','')}</span><br>
                <span style="font-size:12px;color:#6b7280;line-height:1.5">
                  {(ix.get('instruction') or '')[:120]}
                </span>
              </td>
            </tr>"""
    else:
        ix_rows = """
            <tr>
              <td style="padding:16px 12px;color:#6b7280;font-size:14px">
                ✅ No interactions found in your current stack.
              </td>
            </tr>"""

    alert_banner = ""
    if change_alert:
        alert_banner = f"""
        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;
                    padding:14px 16px;margin-bottom:20px">
          <strong style="color:#dc2626">⚠️ New {severity_change['severity']} interaction detected</strong><br>
          <span style="color:#7f1d1d;font-size:13px">{severity_change['message']}</span>
        </div>"""

    med_list  = ", ".join(medications)  or "None saved"
    supp_list = ", ".join(supplements) or "None saved"

    body_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="max-width:560px;margin:32px auto;background:#fff;border-radius:12px;
              overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1)">

    <div style="background:#1A1814;padding:24px 28px;display:flex;align-items:center;gap:12px">
      <span style="font-size:22px">🛡</span>
      <div>
        <div style="color:#D4AF37;font-size:18px;font-weight:700;letter-spacing:0.05em">ELTHIO</div>
        <div style="color:#9ca3af;font-size:12px">Weekly Stack Check</div>
      </div>
    </div>

    <div style="padding:28px">
      {alert_banner}

      <p style="color:#374151;font-size:15px;margin:0 0 20px">
        Here's your weekly supplement safety check for your saved stack.
      </p>

      <div style="background:#f9fafb;border-radius:8px;padding:14px 16px;margin-bottom:20px;
                  font-size:13px;color:#6b7280">
        <strong style="color:#111827;display:block;margin-bottom:6px">Your stack:</strong>
        💊 Medications: {med_list}<br>
        🌿 Supplements: {supp_list}
      </div>

      <strong style="font-size:13px;color:#374151;display:block;margin-bottom:8px">
        Interaction check results:
      </strong>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:20px">
        {ix_rows}
      </table>

      <div style="text-align:center;margin-bottom:24px">
        <a href="{SITE_URL}/?tab=medcheck"
           style="background:#D4AF37;color:#000;padding:12px 28px;border-radius:8px;
                  text-decoration:none;font-weight:600;font-size:14px;display:inline-block">
          Check my stack now →
        </a>
      </div>

      <p style="font-size:11px;color:#9ca3af;line-height:1.6;border-top:1px solid #f3f4f6;
                padding-top:16px;margin:0">
        Educational information only — not medical advice. Always consult your
        pharmacist or doctor before changing your supplement routine.<br><br>
        <a href="{SITE_URL}/unsubscribe?email={urllib.parse.quote(email)}"
           style="color:#9ca3af">Unsubscribe from weekly digests</a>
      </p>
    </div>
  </div>
</body>
</html>"""

    return subject, body_html


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("  STACK SAVE — SELF TEST")
    print("=" * 60)

    test_email = "test@elthio.health"
    test_meds  = ["warfarin", "levothyroxine"]
    test_supps = ["vitamin k2", "magnesium", "fish oil"]

    print("\n[1] Save stack")
    try:
        r = save_stack(test_email, test_meds, test_supps)
        print(f"  ✅ Saved: {r.get('email', r)}")
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n[2] Get stack")
    try:
        r = get_stack(test_email)
        print(f"  ✅ Found: meds={r.get('medications')} supps={r.get('supplements')}")
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n[3] Record check")
    try:
        record_check(test_email, test_meds, test_supps, [
            {"severity": "critical", "id": "warf-k2", "title": "Warfarin + Vitamin K2",
             "instruction": "Monitor INR closely."}
        ])
        print("  ✅ Check recorded")
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n[4] Email (dry run — needs SENDGRID_API_KEY)")
    if not SENDGRID_KEY:
        print("  ⚠  SENDGRID_API_KEY not set — skipping live send")
        subject, _ = _build_email(
            test_email, test_meds, test_supps,
            [{"severity": "critical", "title": "Warfarin + Vitamin K2",
              "instruction": "Monitor INR closely."}],
            None,
        )
        print(f"  Subject would be: {subject}")
    else:
        ok = send_digest_email(
            test_email, test_meds, test_supps,
            [{"severity": "critical", "title": "Warfarin + Vitamin K2",
              "instruction": "Monitor INR closely."}],
        )
        print(f"  {'✅ Sent' if ok else '❌ Failed'}")

    print("\n" + "=" * 60 + "\n")
