"""
rxnorm.py — RxNorm drug name resolution + FDA interaction data

Uses the free NLM RxNav APIs (no API key, no cost) to:
1. Resolve any drug name to a standardized RxCUI code
   ("Lipitor" → 83367, "blood thinner" → 11289)
2. Get FDA-sourced drug interactions for any RxCUI
3. Cross-reference supplement names against RxNorm
4. Build a complete interaction picture from live federal data

Complements the 334-rule curated database:
- RxNorm: drug-drug and drug-class interactions from FDA labels
- 334 rules: supplement-specific intelligence RxNorm doesn't cover

All endpoints are public, free, rate-limit friendly.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

RXNAV_BASE    = "https://rxnav.nlm.nih.gov/REST"
REQUEST_DELAY = 0.2  # seconds between requests — be respectful

# Common colloquial drug names → search terms RxNorm understands
COLLOQUIAL_MAP = {
    "blood thinner":       "warfarin",
    "blood thinners":      "warfarin",
    "anticoagulant":       "warfarin",
    "heart pill":          "metoprolol",
    "heart medication":    "metoprolol",
    "water pill":          "furosemide",
    "water pills":         "furosemide",
    "diuretic":            "furosemide",
    "thyroid pill":        "levothyroxine",
    "thyroid medication":  "levothyroxine",
    "thyroid med":         "levothyroxine",
    "cholesterol pill":    "atorvastatin",
    "cholesterol med":     "atorvastatin",
    "statin":              "atorvastatin",
    "diabetes pill":       "metformin",
    "diabetes medication": "metformin",
    "diabetes med":        "metformin",
    "antidepressant":      "sertraline",
    "ssri":                "sertraline",
    "blood pressure pill": "lisinopril",
    "blood pressure med":  "lisinopril",
    "acid reflux pill":    "omeprazole",
    "acid reflux med":     "omeprazole",
    "ppi":                 "omeprazole",
    "stomach pill":        "omeprazole",
    "steroid":             "prednisone",
    "steroids":            "prednisone",
    "pain pill":           "ibuprofen",
    "painkiller":          "ibuprofen",
    "sleeping pill":       "zolpidem",
    "sleep pill":          "zolpidem",
    "seizure medication":  "phenytoin",
    "seizure med":         "phenytoin",
    "blood sugar pill":    "metformin",
    "insulin":             "insulin",
}

# Supplement names that have RxCUI codes in RxNorm
SUPPLEMENT_RXCUI_MAP = {
    "fish oil":         "1001480",
    "omega-3":          "1001480",
    "coenzyme q10":     "203132",
    "coq10":            "203132",
    "st. john's wort":  "258326",
    "st johns wort":    "258326",
    "melatonin":        "41493",
    "vitamin e":        "11253",
    "vitamin k":        "11256",
    "vitamin k2":       "11256",
    "ginkgo":           "25839",
    "ginkgo biloba":    "25839",
    "garlic":           "4514",
    "ginseng":          "8699",
    "valerian":         "11199",
    "kava":             "41300",
    "echinacea":        "39785",
    "glucosamine":      "41493",
    "calcium":          "1311",
    "iron":             "40798",
    "magnesium":        "11203",
    "zinc":             "11256",
    "vitamin c":        "11253",
    "vitamin d":        "11253",
    "vitamin d3":       "41434",
}


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get(url: str, timeout: int = 10) -> Any:
    """Make a GET request and return parsed JSON."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Elthio/1.0 (supplement safety research; "
                              "contact: research@elthio.health)",
                "Accept":     "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug("RxNav request failed: %s — %s", url[:80], e)
        return None


# ── Name resolution ───────────────────────────────────────────────────────────
def resolve_to_rxcui(drug_name: str) -> dict | None:
    """
    Resolve a drug name to its RxCUI code.

    Tries three approaches in order:
    1. Colloquial map (fast local lookup for common phrases)
    2. Exact RxNorm name lookup
    3. Approximate match (handles brand names, misspellings,
       partial names)

    Returns {
        rxcui: str,
        name:  str,   (normalized RxNorm name)
        tty:   str,   (term type: IN=ingredient, BN=brand, etc.)
        input: str,   (original input)
        method: str,  (how it was resolved)
    } or None if not found.
    """
    drug_lower  = drug_name.lower().strip()
    search_term = COLLOQUIAL_MAP.get(drug_lower, drug_name)

    # Method 1 — exact lookup
    url  = (f"{RXNAV_BASE}/rxcui.json"
            f"?name={urllib.parse.quote(search_term)}&search=2")
    data = _get(url)

    if data:
        rxcui = (data.get("idGroup", {})
                     .get("rxnormId", [None])[0])
        if rxcui:
            log.info("RxNorm exact: '%s' → RxCUI %s", drug_name, rxcui)
            return {
                "rxcui":  rxcui,
                "name":   search_term,
                "input":  drug_name,
                "method": "exact",
            }

    time.sleep(REQUEST_DELAY)

    # Method 2 — approximate match
    url  = (f"{RXNAV_BASE}/approximateTerm.json"
            f"?term={urllib.parse.quote(search_term)}&maxEntries=3")
    data = _get(url)

    if data:
        candidates = (data.get("approximateGroup", {})
                          .get("candidate", []))
        if candidates:
            best  = candidates[0]
            rxcui = best.get("rxcui")
            name  = best.get("name", search_term)
            score = int(best.get("score", 0))

            if rxcui and score >= 50:
                log.info(
                    "RxNorm approx: '%s' → %s (RxCUI %s, score %d)",
                    drug_name, name, rxcui, score
                )
                return {
                    "rxcui":  rxcui,
                    "name":   name,
                    "input":  drug_name,
                    "method": "approximate",
                    "score":  score,
                }

    log.debug("RxNorm: could not resolve '%s'", drug_name)
    return None


def resolve_medications(
    medications: list[str],
) -> dict[str, dict]:
    """
    Resolve a list of medication names to RxCUI codes.
    Returns { original_name: resolution_result } dict.
    Skips medications that can't be resolved.
    """
    resolved = {}
    for med in medications:
        result = resolve_to_rxcui(med)
        if result:
            resolved[med] = result
        time.sleep(REQUEST_DELAY)
    log.info(
        "Resolved %d/%d medications to RxCUI",
        len(resolved), len(medications)
    )
    return resolved


# ── Interaction lookup ────────────────────────────────────────────────────────
def get_interactions_for_rxcui(rxcui: str) -> list[dict]:
    """
    Get drug interactions for a single RxCUI from RxNav.
    Returns list of interaction dicts.
    """
    url  = f"{RXNAV_BASE}/interaction/interaction.json?rxcui={rxcui}"
    data = _get(url)

    if not data:
        return []

    interactions = []
    groups = (data.get("interactionTypeGroup") or [])

    for group in groups:
        source = group.get("sourceDisclaimer", "")
        for itype in (group.get("interactionType") or []):
            concept1 = itype.get("minConceptItem", {})
            for pair in (itype.get("interactionPair") or []):
                concept2    = pair.get("interactionConcept", [{}])[-1]
                description = pair.get("description", "")
                severity    = pair.get("severity", "").lower()

                interactions.append({
                    "rxcui_1":     rxcui,
                    "drug_1":      concept1.get("name", ""),
                    "rxcui_2":     concept2.get("minConceptItem", {}).get("rxcui", ""),
                    "drug_2":      concept2.get("minConceptItem", {}).get("name", ""),
                    "description": description,
                    "severity":    severity or "moderate",
                    "source":      source[:100] if source else "RxNorm/NLM",
                })

    log.info(
        "RxNav: %d interactions found for RxCUI %s",
        len(interactions), rxcui
    )
    return interactions


def get_interactions_for_list(rxcui_list: list[str]) -> list[dict]:
    """
    Get interactions between multiple drugs simultaneously.
    More efficient than individual lookups for multi-drug stacks.
    """
    if len(rxcui_list) < 2:
        return []

    rxcuis_str = "+".join(rxcui_list[:8])  # API limit
    url        = (f"{RXNAV_BASE}/interaction/list.json"
                  f"?rxcuis={rxcuis_str}")
    data       = _get(url)

    if not data:
        return []

    interactions = []
    full_data    = data.get("fullInteractionTypeGroup") or []

    for group in full_data:
        source = group.get("sourceDisclaimer", "")
        for itype in (group.get("fullInteractionType") or []):
            for pair in (itype.get("interactionPair") or []):
                concepts    = pair.get("interactionConcept", [])
                description = pair.get("description", "")
                severity    = pair.get("severity", "").lower()

                if len(concepts) >= 2:
                    interactions.append({
                        "drug_1":      concepts[0].get(
                            "minConceptItem", {}
                        ).get("name", ""),
                        "rxcui_1":     concepts[0].get(
                            "minConceptItem", {}
                        ).get("rxcui", ""),
                        "drug_2":      concepts[1].get(
                            "minConceptItem", {}
                        ).get("name", ""),
                        "rxcui_2":     concepts[1].get(
                            "minConceptItem", {}
                        ).get("rxcui", ""),
                        "description": description,
                        "severity":    severity or "moderate",
                        "source":      "NLM RxNav Drug Interaction API",
                    })

    log.info(
        "RxNav list: %d interactions for %d drugs",
        len(interactions), len(rxcui_list)
    )
    return interactions


# ── Supplement RxCUI lookup ───────────────────────────────────────────────────
def get_supplement_rxcui(supplement_name: str) -> str | None:
    """
    Get RxCUI for a supplement if it's in RxNorm.
    Uses local map first, then tries RxNav.
    """
    supp_lower = supplement_name.lower().strip()

    # Check local map first
    for key, rxcui in SUPPLEMENT_RXCUI_MAP.items():
        if key in supp_lower or supp_lower in key:
            return rxcui

    # Try RxNav
    result = resolve_to_rxcui(supplement_name)
    return result.get("rxcui") if result else None


# ── Main entry point ──────────────────────────────────────────────────────────
def get_rxnorm_context(
    medications:  list[str],
    supplements:  list[str],
) -> dict:
    """
    Main entry point for ai_med_check.py.
    Resolves all medications to RxCUI codes, gets live FDA
    interaction data, and returns structured context.

    Returns {
        resolved_meds:    { name: { rxcui, normalized_name } },
        drug_interactions: [ interaction dicts ],
        supp_rxcuis:      { supp_name: rxcui },
        context_text:     str,  (formatted for Claude)
        rxcui_list:       [ rxcui strings ],
    }
    """
    # 1. Resolve medications to RxCUI
    resolved_meds = resolve_medications(medications)

    if not resolved_meds:
        return {
            "resolved_meds":     {},
            "drug_interactions": [],
            "supp_rxcuis":       {},
            "context_text":      "",
            "rxcui_list":        [],
        }

    rxcui_list = [r["rxcui"] for r in resolved_meds.values()]

    # 2. Get supplement RxCUIs
    supp_rxcuis = {}
    for supp in supplements:
        rxcui = get_supplement_rxcui(supp)
        if rxcui:
            supp_rxcuis[supp] = rxcui

    # 3. Add supplement RxCUIs to the interaction query
    all_rxcuis = list(set(rxcui_list + list(supp_rxcuis.values())))

    # 4. Get interactions
    drug_interactions = []
    if len(all_rxcuis) >= 2:
        drug_interactions = get_interactions_for_list(all_rxcuis)

    # Fallback to individual lookups if list query returns fewer than 2 results
    if len(drug_interactions) < 2 and rxcui_list:
        for rxcui in rxcui_list[:3]:
            ixs = get_interactions_for_rxcui(rxcui)
            drug_interactions.extend(ixs)
            time.sleep(REQUEST_DELAY)

    # Filter out low-quality/empty results
    drug_interactions = [
        ix for ix in drug_interactions
        if ix.get("description") and len(ix["description"]) > 20
    ]

    # 5. Build context text for Claude
    context_text = _build_context_text(
        resolved_meds, drug_interactions, supp_rxcuis
    )

    return {
        "resolved_meds":     resolved_meds,
        "drug_interactions": drug_interactions[:15],
        "supp_rxcuis":       supp_rxcuis,
        "context_text":      context_text,
        "rxcui_list":        rxcui_list,
    }


def _build_context_text(
    resolved_meds:     dict,
    drug_interactions: list[dict],
    supp_rxcuis:       dict,
) -> str:
    """Build structured context text for Claude."""
    if not resolved_meds and not drug_interactions:
        return ""

    parts = ["RXNORM DRUG RESOLUTION:"]

    for original, result in resolved_meds.items():
        normalized = result.get("name", original)
        rxcui      = result.get("rxcui", "")
        method     = result.get("method", "")
        if normalized.lower() != original.lower():
            parts.append(
                f"  '{original}' resolved to: {normalized} "
                f"(RxCUI {rxcui}, via {method})"
            )
        else:
            parts.append(f"  {normalized} (RxCUI {rxcui})")

    if supp_rxcuis:
        parts.append("\nSUPPLEMENTS WITH RXNORM CODES:")
        for supp, rxcui in supp_rxcuis.items():
            parts.append(f"  {supp} (RxCUI {rxcui})")

    if drug_interactions:
        parts.append(
            f"\nFDA-SOURCED INTERACTIONS ({len(drug_interactions)} found):"
        )
        severity_order = {
            "high": 0, "moderate": 1, "low": 2, "": 3
        }
        sorted_ixs = sorted(
            drug_interactions,
            key=lambda x: severity_order.get(
                x.get("severity", "").lower(), 3
            )
        )
        for ix in sorted_ixs[:8]:
            sev  = ix.get("severity", "moderate").upper()
            d1   = ix.get("drug_1", "")
            d2   = ix.get("drug_2", "")
            desc = ix.get("description", "")[:150]
            src  = ix.get("source", "RxNorm")
            parts.append(
                f"  [{sev}] {d1} ↔ {d2}: {desc} (Source: {src})"
            )
    else:
        parts.append(
            "\nNo drug-drug interactions found in RxNorm for this stack."
        )

    return "\n".join(parts)


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("\n=== RXNORM SELF TEST ===\n")

    print("[1] Exact name resolution")
    r = resolve_to_rxcui("warfarin")
    print(f"  warfarin → RxCUI {r['rxcui'] if r else 'NOT FOUND'}")

    print("\n[2] Brand name resolution")
    r2 = resolve_to_rxcui("Lipitor")
    print(f"  Lipitor → {r2['name'] if r2 else 'NOT FOUND'} "
          f"(RxCUI {r2['rxcui'] if r2 else '—'})")

    print("\n[3] Colloquial name resolution")
    r3 = resolve_to_rxcui("blood thinner")
    print(f"  'blood thinner' → {r3['name'] if r3 else 'NOT FOUND'} "
          f"(via {r3.get('method','—') if r3 else '—'})")

    print("\n[4] Supplement RxCUI lookup")
    rxcui = get_supplement_rxcui("fish oil")
    print(f"  fish oil → RxCUI {rxcui or 'NOT FOUND'}")

    print("\n[5] Full stack resolution")
    ctx = get_rxnorm_context(
        medications=["warfarin", "atorvastatin", "metformin"],
        supplements=["fish oil", "coq10", "vitamin k2"],
    )
    print(f"  Resolved meds: {len(ctx['resolved_meds'])}")
    print(f"  Drug interactions: {len(ctx['drug_interactions'])}")
    print(f"  Supplement RxCUIs: {len(ctx['supp_rxcuis'])}")
    if ctx['context_text']:
        print("\n  Context preview:")
        for line in ctx['context_text'].split('\n')[:8]:
            print(f"    {line}")

    print("\n=== TEST COMPLETE ===\n")
