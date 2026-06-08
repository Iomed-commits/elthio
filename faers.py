"""
faers.py — FDA Adverse Event Reporting System integration

Pulls real-world adverse event counts for drug+supplement combinations
from the OpenFDA FAERS API. Free, no API key required.

This adds a fundamentally different data layer to Med Check:
- Current rules: curated interaction pairs (114 rules)
- FAERS: real people who reported real symptoms combining specific drugs + supplements
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

FAERS_BASE = "https://api.fda.gov/drug/event.json"

SUPPLEMENT_FAERS_TERMS = {
    "fish oil":        ["fish oil", "omega-3", "omega 3 fatty acid"],
    "vitamin k":       ["vitamin k", "phylloquinone", "menaquinone"],
    "vitamin k2":      ["vitamin k2", "menaquinone", "mk7", "mk-7"],
    "st. john's wort": ["hypericum", "st john", "hypericum perforatum"],
    "ginkgo":          ["ginkgo", "ginkgo biloba"],
    "garlic":          ["garlic", "allium sativum"],
    "coq10":           ["coenzyme q10", "ubiquinol", "ubiquinone"],
    "magnesium":       ["magnesium"],
    "calcium":         ["calcium"],
    "iron":            ["iron supplement", "ferrous sulfate", "ferrous gluconate"],
    "vitamin e":       ["vitamin e", "tocopherol"],
    "vitamin d":       ["vitamin d", "cholecalciferol"],
    "melatonin":       ["melatonin"],
    "ashwagandha":     ["ashwagandha", "withania somnifera"],
    "turmeric":        ["turmeric", "curcumin", "curcuma longa"],
    "berberine":       ["berberine"],
    "valerian":        ["valerian", "valeriana officinalis"],
    "echinacea":       ["echinacea"],
    "ginseng":         ["ginseng", "panax ginseng"],
    "probiotics":      ["probiotic", "lactobacillus", "bifidobacterium"],
}


def _get_json(url: str, timeout: int = 10) -> Any:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Elthio/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug("FAERS request failed: %s", e)
        return None


def get_adverse_events(
    drug_name: str,
    supplement_name: str,
    limit: int = 10,
) -> dict:
    """
    Query FAERS for adverse events involving both a drug and supplement.
    Returns {
        total_events: int,
        top_reactions: [{"reaction": str, "count": int}],
        serious_count: int,
        death_count: int,
        source_url: str,
        drug_searched: str,
        supplement_searched: str,
    }
    """
    supp_lower = supplement_name.lower()
    faers_terms = None
    for key, terms in SUPPLEMENT_FAERS_TERMS.items():
        if key in supp_lower or supp_lower in key:
            faers_terms = terms
            break
    if not faers_terms:
        faers_terms = [supplement_name]

    drug_encoded = urllib.parse.quote(f'"{drug_name}"')
    supp_term    = faers_terms[0]
    supp_encoded = urllib.parse.quote(f'"{supp_term}"')

    search = (
        f"patient.drug.medicinalproduct:{drug_encoded}"
        f"+AND+patient.drug.medicinalproduct:{supp_encoded}"
    )
    url = f"{FAERS_BASE}?search={search}&count=patient.reaction.reactionmeddrapt.exact&limit={limit}"

    data = _get_json(url)

    if not data or "results" not in data:
        drug_broad = urllib.parse.quote(drug_name)
        supp_broad = urllib.parse.quote(supp_term)
        search2 = (
            f"patient.drug.medicinalproduct:{drug_broad}"
            f"+AND+patient.drug.medicinalproduct:{supp_broad}"
        )
        url2 = f"{FAERS_BASE}?search={search2}&count=patient.reaction.reactionmeddrapt.exact&limit={limit}"
        data = _get_json(url2)
        url  = url2
        search = search2

    if not data or "results" not in data:
        return {
            "total_events":        0,
            "top_reactions":       [],
            "serious_count":       0,
            "death_count":         0,
            "source_url":          url,
            "drug_searched":       drug_name,
            "supplement_searched": supp_term,
            "found":               False,
        }

    total  = sum(r.get("count", 0) for r in data.get("results", []))
    if not total:
        total = data.get("meta", {}).get("results", {}).get("total", 0)
    top_rx = [
        {"reaction": r["term"].title(), "count": r["count"]}
        for r in data["results"][:10]
    ]

    serious_url = f"{FAERS_BASE}?search={search}+AND+serious:1&limit=1"
    serious_data = _get_json(serious_url)
    serious_count = (
        serious_data.get("meta", {}).get("results", {}).get("total", 0)
        if serious_data else 0
    )

    death_url = f"{FAERS_BASE}?search={search}+AND+seriousnessdeath:1&limit=1"
    death_data = _get_json(death_url)
    death_count = (
        death_data.get("meta", {}).get("results", {}).get("total", 0)
        if death_data else 0
    )

    return {
        "total_events":        total,
        "top_reactions":       top_rx,
        "serious_count":       serious_count,
        "death_count":         death_count,
        "source_url":          url,
        "drug_searched":       drug_name,
        "supplement_searched": supp_term,
        "found":               total > 0,
    }


def get_faers_context_for_stack(
    medications: list[str],
    supplements: list[str],
) -> list[dict]:
    """Get FAERS context for all medication-supplement pairs. Only pairs with >0 events."""
    results = []
    for med in medications[:3]:
        for supp in supplements[:5]:
            try:
                data = get_adverse_events(med, supp)
                if data.get("total_events", 0) > 0:
                    results.append({
                        "drug":       med,
                        "supplement": supp,
                        "faers":      data,
                    })
            except Exception as e:
                log.warning("FAERS error for %s + %s: %s", med, supp, e)
    return results


if __name__ == "__main__":
    print("\n=== FAERS SELF TEST ===\n")

    print("[1] Warfarin + Fish Oil")
    r = get_adverse_events("warfarin", "fish oil")
    print(f"  Total events: {r['total_events']}")
    print(f"  Serious: {r['serious_count']}, Deaths: {r['death_count']}")
    print(f"  Top reactions: {[x['reaction'] for x in r['top_reactions'][:5]]}")

    print("\n[2] Metformin + Berberine")
    r2 = get_adverse_events("metformin", "berberine")
    print(f"  Total events: {r2['total_events']}")
    print(f"  Top reactions: {[x['reaction'] for x in r2['top_reactions'][:3]]}")

    print("\n[3] Stack context (warfarin + [fish oil, coq10])")
    ctx = get_faers_context_for_stack(["warfarin"], ["fish oil", "coq10"])
    for c in ctx:
        print(f"  {c['drug']} + {c['supplement']}: "
              f"{c['faers']['total_events']} events")
    print()
