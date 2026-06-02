"""
Med Check engine — curated drug–supplement interactions + NIH RxNorm lookup.

Educational only. Matches user meds/supplements/audited ingredients against a
pharmacist-curated dataset with citable sources (not a live interaction API).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("elthio.med_check")

_DB_PATH = Path(__file__).resolve().parent / "interactions_db.json"
_RXNAV = "https://rxnav.nlm.nih.gov/REST"
_CACHE: dict[str, dict | None] = {}

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "informational": 3}

SEVERITY_STYLES = {
    "critical": {"label": "Critical", "css_class": "danger"},
    "high": {"label": "High", "css_class": "warning"},
    "moderate": {"label": "Moderate", "css_class": "info"},
    "informational": {"label": "Informational", "css_class": "savings"},
}

# Legacy visit_packet / older UI
_LEGACY_SEVERITY = {
    "critical": "severe",
    "high": "severe",
    "moderate": "moderate",
    "informational": "mild",
    "severe": "severe",
    "mild": "mild",
    "info": "mild",
}


def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _matches(user_input: str, keyword: str) -> bool:
    """
    True if either string contains the other after normalization.
    """
    n = _normalize(user_input)
    k = _normalize(keyword)
    if not n or not k:
        return False
    return k in n or n in k


def _matches_any(user_input: str, keywords: list) -> bool:
    """True if user_input matches ANY keyword in the list."""
    return any(_matches(user_input, kw) for kw in (keywords or []))


def _load_db() -> list[dict]:
    if not _DB_PATH.is_file():
        return []
    raw = json.loads(_DB_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        # New schema
        if "med_keywords" in row or "supp_keywords" in row:
            out.append(row)
            continue
        # Legacy schema → new shape
        out.append(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "severity": _normalize_severity(row.get("severity", "moderate")),
                "med_keywords": row.get("drugs") or row.get("med_keywords") or [],
                "supp_keywords": row.get("supplements") or row.get("supp_keywords") or [],
                "detail": row.get("detail", ""),
                "instruction": row.get("action") or row.get("instruction", ""),
                "monitor": row.get("monitor"),
                "source": _legacy_source(row),
                "drug_rxcuis": row.get("drug_rxcuis") or [],
            }
        )
    return out


def _legacy_source(row: dict) -> str:
    sources = row.get("sources") or []
    if sources and isinstance(sources[0], dict):
        return sources[0].get("label") or "NIH / FDA references"
    return row.get("source") or "NIH / FDA references"


def _normalize_severity(sev: str | None) -> str:
    s = (sev or "moderate").lower().strip()
    if s in ("severe", "critical"):
        return "critical"
    if s in ("high",):
        return "high"
    if s in ("mild", "info", "informational"):
        return "informational" if s in ("info", "informational") else "moderate"
    if s in SEVERITY_ORDER:
        return s
    return "moderate"


def lookup_rxnorm(drug_name: str, *, timeout: float = 2.5) -> dict | None:
    """Resolve a medication string via NIH RxNorm (free public API)."""
    if os.environ.get("ELTHIO_SKIP_RXNORM", "").strip().lower() in ("1", "true", "yes"):
        return None
    key = _normalize(drug_name)
    if not key:
        return None
    if key in _CACHE:
        return _CACHE[key]

    result: dict | None = None
    try:
        q = urllib.parse.quote(drug_name.strip())
        url = f"{_RXNAV}/rxcui.json?name={q}&search=2"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        ids = (data.get("idGroup") or {}).get("rxnormId") or []
        if not ids:
            approx = f"{_RXNAV}/approximateTerm.json?term={q}&maxEntries=1"
            with urllib.request.urlopen(approx, timeout=timeout) as resp:
                approx_data = json.loads(resp.read().decode())
            candidates = (approx_data.get("approximateGroup") or {}).get("candidate") or []
            if isinstance(candidates, dict):
                candidates = [candidates]
            if candidates:
                ids = [candidates[0].get("rxcui")]
        if not ids:
            _CACHE[key] = None
            return None

        rxcui = str(ids[0])
        prop_url = f"{_RXNAV}/rxcui/{rxcui}/properties.json"
        with urllib.request.urlopen(prop_url, timeout=timeout) as resp:
            props = json.loads(resp.read().decode())
        prop = props.get("properties") or {}
        result = {
            "rxcui": rxcui,
            "name": prop.get("name") or drug_name.strip(),
            "tty": prop.get("tty"),
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        log.debug("RxNorm lookup failed for %r: %s", drug_name, e)
        result = None

    _CACHE[key] = result
    return result


def _resolve_medications(medications: list[str]) -> list[dict]:
    out = []
    for raw in medications:
        name = (raw or "").strip()
        if not name:
            continue
        rx = lookup_rxnorm(name)
        out.append(
            {
                "input": name,
                "rxcui": rx.get("rxcui") if rx else None,
                "rxnorm_name": rx.get("name") if rx else None,
            }
        )
    return out


def _supplement_terms(supplements: list[str], ingredients: list[dict]) -> list[dict]:
    terms: list[dict] = []
    for s in supplements:
        s = (s or "").strip()
        if s:
            terms.append({"label": s, "display": s, "kind": "supplement"})
    for ing in ingredients:
        name = (ing.get("name") or "").strip()
        if not name:
            continue
        amt, unit = ing.get("amount"), ing.get("unit") or ""
        dose = f" ({amt} {unit})".rstrip() if amt is not None else ""
        src = ing.get("source") or ing.get("source_product") or ""
        display = f"{name}{dose}" + (f" — {src}" if src else "")
        terms.append(
            {
                "label": name,
                "display": display.strip(),
                "kind": "ingredient",
                "amount": amt,
                "unit": unit,
            }
        )
    return terms


def _row_matches(
    row: dict,
    resolved_meds: list[dict],
    supp_terms: list[dict],
) -> tuple[bool, list[dict], list[str]]:
    med_keywords = row.get("med_keywords") or []
    supp_keywords = row.get("supp_keywords") or []
    pair_type = row.get("pair_type") or "drug_supplement"
    supp_labels = [t["label"] for t in supp_terms]

    if pair_type == "supplement_supplement":
        med_hit = any(_matches_any(lbl, med_keywords) for lbl in supp_labels)
        supp_hit = any(_matches_any(lbl, supp_keywords) for lbl in supp_labels)
        if not (med_hit and supp_hit):
            return False, [], []
        matched_supps = list(
            dict.fromkeys(
                t["display"]
                for t in supp_terms
                if _matches_any(t["label"], med_keywords)
                or _matches_any(t["label"], supp_keywords)
            )
        )
        return True, [], matched_supps

    med_strings: list[str] = []
    for m in resolved_meds:
        if m.get("input"):
            med_strings.append(m["input"])
        if m.get("rxnorm_name"):
            med_strings.append(m["rxnorm_name"])

    med_hit = any(_matches_any(med, med_keywords) for med in med_strings)
    if not med_hit:
        rx_list = [str(x) for x in (row.get("drug_rxcuis") or [])]
        med_hit = any(
            m.get("rxcui") and str(m.get("rxcui")) in rx_list for m in resolved_meds
        )

    supp_hit = any(_matches_any(supp, supp_keywords) for supp in supp_labels)
    if not (med_hit and supp_hit):
        return False, [], []

    rx_list = [str(x) for x in (row.get("drug_rxcuis") or [])]
    matched_meds = [
        m
        for m in resolved_meds
        if _matches_any(m.get("input") or "", med_keywords)
        or _matches_any(m.get("rxnorm_name") or "", med_keywords)
        or (m.get("rxcui") and str(m.get("rxcui")) in rx_list)
    ]
    matched_supps = [
        t["display"] for t in supp_terms if _matches_any(t["label"], supp_keywords)
    ]
    if not matched_meds or not matched_supps:
        return False, [], []

    return True, matched_meds, matched_supps


def _interaction_payload(row: dict, matched_meds: list[dict], matched_supps: list[str]) -> dict:
    sev = _normalize_severity(row.get("severity"))
    style = SEVERITY_STYLES.get(sev, SEVERITY_STYLES["moderate"])
    payload = {
        "id": row.get("id"),
        "title": row.get("title"),
        "severity": sev,
        "severity_label": style["label"],
        "severity_css_class": style["css_class"],
        "detail": row.get("detail"),
        "instruction": row.get("instruction"),
        "source": row.get("source"),
        "matched_medications": [
            {
                "input": m["input"],
                "rxnorm_name": m.get("rxnorm_name"),
                "rxcui": m.get("rxcui"),
            }
            for m in matched_meds
        ],
        "matched_supplements": matched_supps,
    }
    if row.get("monitor"):
        payload["monitor"] = row["monitor"]
    return payload


def get_near_misses(
    med: str,
    supp: str,
    all_interactions: list[dict],
    *,
    matched_ids: set[str],
) -> list[str]:
    """
    When med+supp have no direct match, check if the med or supp appears
    in other curated rows. Return plain-English near-miss strings.
    """
    messages: list[str] = []
    med_hits = [
        r
        for r in all_interactions
        if r.get("id") not in matched_ids
        and (r.get("pair_type") or "drug_supplement") == "drug_supplement"
        and _matches_any(med, r.get("med_keywords") or [])
    ]
    if med_hits:
        other_supps: list[str] = []
        for r in med_hits:
            if _matches_any(supp, r.get("supp_keywords") or []):
                continue
            for kw in r.get("supp_keywords") or []:
                if kw and kw not in other_supps:
                    other_supps.append(kw)
        if other_supps:
            sample = ", ".join(other_supps[:4])
            messages.append(
                f"{med} is in our database — flagged with {sample}, not with {supp}."
            )

    supp_hits = [
        r
        for r in all_interactions
        if r.get("id") not in matched_ids
        and (r.get("pair_type") or "drug_supplement") == "drug_supplement"
        and _matches_any(supp, r.get("supp_keywords") or [])
    ]
    if supp_hits:
        other_meds: list[str] = []
        for r in supp_hits:
            if _matches_any(med, r.get("med_keywords") or []):
                continue
            for kw in r.get("med_keywords") or []:
                if kw and kw not in other_meds:
                    other_meds.append(kw)
        if other_meds:
            sample = ", ".join(other_meds[:4])
            messages.append(
                f"{supp} is in our database — flagged with {sample}, not with {med}."
            )

    return messages


def run_med_check(
    medications: list[str],
    supplements: list[str],
    ingredients: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Return documented interaction flags for pharmacist discussion.
    ingredients: optional audited rows {name, amount?, unit?, source?}
    """
    ingredients = ingredients or []
    db = _load_db()
    resolved_meds = _resolve_medications(medications)
    supp_terms = _supplement_terms(supplements, ingredients)

    interactions: list[dict] = []
    matched_ids: set[str] = set()
    matched_pairs: set[tuple[str, str]] = set()

    for row in db:
        med_keywords = row.get("med_keywords") or []
        supp_keywords = row.get("supp_keywords") or []
        pair_type = row.get("pair_type") or "drug_supplement"
        supp_labels = [t["label"] for t in supp_terms]

        if pair_type == "supplement_supplement":
            med_hit = any(_matches_any(lbl, med_keywords) for lbl in supp_labels)
            supp_hit = any(_matches_any(lbl, supp_keywords) for lbl in supp_labels)
        else:
            med_strings = [m["input"] for m in resolved_meds if m.get("input")]
            for m in resolved_meds:
                if m.get("rxnorm_name"):
                    med_strings.append(m["rxnorm_name"])
            med_hit = any(_matches_any(med, med_keywords) for med in med_strings)
            if not med_hit:
                rx_list = [str(x) for x in (row.get("drug_rxcuis") or [])]
                med_hit = any(
                    m.get("rxcui") and str(m.get("rxcui")) in rx_list
                    for m in resolved_meds
                )
            supp_hit = any(_matches_any(supp, supp_keywords) for supp in supp_labels)

        if not (med_hit and supp_hit):
            continue

        ok, matched_meds, matched_supps = _row_matches(row, resolved_meds, supp_terms)
        if not ok:
            continue

        rid = str(row.get("id") or "")
        if rid in matched_ids:
            continue
        matched_ids.add(rid)
        interactions.append(_interaction_payload(row, matched_meds, matched_supps))
        for m in matched_meds or [{"input": ""}]:
            for s in matched_supps:
                med_key = m.get("input") if isinstance(m, dict) else ""
                matched_pairs.add((med_key.lower(), s.lower()))

    interactions.sort(key=lambda x: SEVERITY_ORDER.get(x.get("severity", "moderate"), 9))

    near_misses: list[str] = []
    seen_nm: set[str] = set()
    med_names = [m["input"] for m in resolved_meds]
    supp_names = [t["label"] for t in supp_terms]

    for med in med_names:
        for supp in supp_names:
            pair_key = (med.lower(), supp.lower())
            if pair_key in matched_pairs:
                continue
            direct = any(
                _row_matches(row, resolved_meds, supp_terms)[0]
                for row in db
                if _matches_any(med, row.get("med_keywords") or [])
                and _matches_any(supp, row.get("supp_keywords") or [])
            )
            if direct:
                continue
            for msg in get_near_misses(med, supp, db, matched_ids=matched_ids):
                if msg not in seen_nm:
                    seen_nm.add(msg)
                    near_misses.append(msg)

    checked_pairs = len(med_names) * len(supp_names) if med_names and supp_names else 0

    # Backward compatibility for visit_packet.html
    findings = []
    for it in interactions:
        leg_sev = _LEGACY_SEVERITY.get(it.get("severity", "moderate"), "moderate")
        findings.append(
            {
                **it,
                "severity": leg_sev,
                "action": it.get("instruction"),
                "icon": "🚫" if leg_sev == "severe" else "⚠️",
                "sources": [{"label": it.get("source")}] if it.get("source") else [],
            }
        )

    disclaimer = (
        "Educational information only — not medical advice. "
        "No result means no match in our curated set, not that your combination is safe. "
        "Always tell your doctor and pharmacist every supplement you take."
    )

    return {
        "interactions": interactions,
        "near_misses": near_misses,
        "checked_pairs": checked_pairs,
        "rules_checked": len(db),
        "findings": findings,
        "resolved_medications": resolved_meds,
        "supplement_terms_checked": [t["display"] for t in supp_terms],
        "meta": {
            "curated_interactions": len(db),
            "rxnorm_api": "https://rxnav.nlm.nih.gov/",
            "positioning": "Flags well-documented interactions worth discussing with your pharmacist.",
        },
        "disclaimer": disclaimer,
        "severity_styles": SEVERITY_STYLES,
    }


if __name__ == "__main__":
    import json

    os.environ["ELTHIO_SKIP_RXNORM"] = "1"

    tests = [
        (["warfarin"], ["vitamin k2"], "critical", True),
        (["warfarin"], ["omega-3 fish oil"], "high", True),
        (["warfarin"], ["st. john's wort"], "critical", True),
        (["levothyroxine"], ["magnesium glycinate"], "critical", True),
        (["levothyroxine"], ["calcium carbonate"], "critical", True),
        (["metformin"], ["vitamin b12"], "high", True),
        (["sertraline"], ["st. john's wort"], "critical", True),
        (["atorvastatin"], ["red yeast rice"], "critical", True),
        (["metformin"], ["vitamin k2"], None, False),
    ]

    all_passed = True
    for meds, supps, expected_sev, should_match in tests:
        result = run_med_check(meds, supps, [])
        interactions = result.get("interactions", [])
        matched = len(interactions) > 0
        nm = len(result.get("near_misses", []))

        if should_match:
            passed = matched and any(i["severity"] == expected_sev for i in interactions)
        else:
            passed = not matched

        status = "✓" if passed else "✗ FAIL"
        if not passed:
            all_passed = False

        print(f"{status}  {meds[0]} + {supps[0]}")
        for i in interactions:
            print(f"      [{i['severity'].upper()}] {i['title']}")
        if nm:
            print(f"      ~ {nm} near-miss(es)")

    print()
    print("All tests passed ✓" if all_passed else "SOME TESTS FAILED ✗")
