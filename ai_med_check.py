"""
ai_med_check.py — Elthio AI-powered Med Check
Uses Claude + RxNorm + OpenFDA + PubChem + MedlinePlus to resolve
natural language queries, check the 114-rule database, and explain
findings in plain English with citations.
"""
from __future__ import annotations
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
import concurrent.futures
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"


def _anthropic_key() -> str:
    """Read at call time so Railway/env injections are always picked up."""
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def claude_configured() -> bool:
    key = _anthropic_key()
    return key.startswith("sk-ant")
OPENFDA_BASE      = "https://api.fda.gov/drug/label.json"

# ── Common phrase → drug resolution (no API call needed) ─────────────────────
COMMON_RESOLUTIONS = {
    "blood thinner":       ["warfarin", "apixaban", "rivaroxaban"],
    "blood thinners":      ["warfarin", "apixaban", "rivaroxaban"],
    "anticoagulant":       ["warfarin", "apixaban", "rivaroxaban"],
    "thyroid pill":        ["levothyroxine"],
    "thyroid med":         ["levothyroxine"],
    "thyroid medication":  ["levothyroxine"],
    "water pill":          ["hydrochlorothiazide", "furosemide"],
    "water pills":         ["hydrochlorothiazide", "furosemide"],
    "diuretic":            ["hydrochlorothiazide", "furosemide"],
    "statin":              ["atorvastatin", "simvastatin", "rosuvastatin"],
    "cholesterol pill":    ["atorvastatin", "simvastatin"],
    "antidepressant":      ["sertraline", "escitalopram", "fluoxetine"],
    "ssri":                ["sertraline", "escitalopram", "fluoxetine"],
    "sleeping pill":       ["zolpidem", "eszopiclone"],
    "heart pill":          ["metoprolol", "carvedilol", "digoxin"],
    "diabetes pill":       ["metformin", "glipizide"],
    "diabetes med":        ["metformin"],
    "blood pressure pill": ["lisinopril", "amlodipine", "losartan"],
    "painkiller":          ["ibuprofen", "naproxen", "acetaminophen"],
    "antacid":             ["omeprazole", "pantoprazole", "famotidine"],
    "acid reflux pill":    ["omeprazole", "esomeprazole"],
    "transplant med":      ["tacrolimus", "cyclosporine"],
    "seizure med":         ["phenytoin", "levetiracetam", "carbamazepine"],
    "mood stabilizer":     ["lithium", "valproate", "lamotrigine"],
    "anxiety pill":        ["alprazolam", "lorazepam", "buspirone"],
}

OPENFDA_SUPPLEMENT_FIELDS = [
    "drug_interactions", "warnings", "precautions",
    "warnings_and_cautions", "food_safety_warnings",
    "information_for_patients",
]

SUPPLEMENT_KEYWORDS = [
    "vitamin", "supplement", "herbal", "herb", "mineral",
    "omega", "fish oil", "calcium", "magnesium", "zinc",
    "iron", "potassium", "coq10", "coenzyme", "ginkgo",
    "st. john", "echinacea", "garlic", "turmeric", "ginseng",
    "melatonin", "valerian", "kava", "ashwagandha", "berberine",
    "natural", "botanical", "dietary",
]

# Instant supplement resolution (no Claude needed)
COMMON_SUPPLEMENT_PHRASES = [
    "st. john's wort", "st. john's", "st. john", "fish oil", "omega-3",
    "omega 3", "vitamin k2", "vitamin k", "vitamin d3", "vitamin d",
    "vitamin b12", "vitamin c", "coenzyme q10", "coq10", "red yeast rice",
    "magnesium", "turmeric", "ashwagandha", "berberine", "calcium",
    "zinc", "iron", "potassium", "garlic", "ginkgo", "ginseng",
    "melatonin", "valerian", "echinacea", "kava", "biotin", "selenium",
]

# Known nutrient depletions and gaps caused by medications
MEDICATION_GAPS: dict[str, Any] = {
    "metformin": [
        {
            "nutrient":    "vitamin b12",
            "reason":      "Metformin reduces B12 absorption by blocking the calcium-dependent uptake mechanism in the terminal ileum.",
            "severity":    "high",
            "instruction": "Consider 1000mcg methylcobalamin B12 daily. Get B12 levels checked annually if on metformin long-term.",
            "source":      "New England Journal of Medicine",
            "evidence":    "strong",
        },
        {
            "nutrient":    "folate",
            "reason":      "Metformin can modestly reduce folate levels over time.",
            "severity":    "moderate",
            "instruction": "Ensure adequate folate intake through diet or a B-complex supplement.",
            "source":      "Diabetes Care",
            "evidence":    "moderate",
        },
    ],
    "atorvastatin": [
        {
            "nutrient":    "coq10",
            "reason":      "Statins block the mevalonate pathway which is required for both cholesterol AND CoQ10 synthesis. All statins deplete CoQ10.",
            "severity":    "high",
            "instruction": "Take 100-200mg CoQ10 daily (ubiquinol form for better absorption). Especially important if experiencing muscle weakness.",
            "source":      "Biofactors Journal",
            "evidence":    "strong",
        },
    ],
    "simvastatin": [
        {
            "nutrient":    "coq10",
            "reason":      "Statins block the mevalonate pathway which is required for both cholesterol AND CoQ10 synthesis.",
            "severity":    "high",
            "instruction": "Take 100-200mg CoQ10 daily (ubiquinol form for better absorption).",
            "source":      "Biofactors Journal",
            "evidence":    "strong",
        },
    ],
    "rosuvastatin": [
        {
            "nutrient":    "coq10",
            "reason":      "Statins block CoQ10 synthesis via the mevalonate pathway.",
            "severity":    "high",
            "instruction": "Take 100-200mg CoQ10 daily.",
            "source":      "Biofactors Journal",
            "evidence":    "strong",
        },
    ],
    "lovastatin": [
        {
            "nutrient":    "coq10",
            "reason":      "Statins block CoQ10 synthesis via the mevalonate pathway.",
            "severity":    "high",
            "instruction": "Take 100-200mg CoQ10 daily.",
            "source":      "Biofactors Journal",
            "evidence":    "strong",
        },
    ],
    "omeprazole": [
        {
            "nutrient":    "magnesium",
            "reason":      "Long-term PPI use reduces magnesium absorption. Hypomagnesemia is an FDA-recognized risk of PPIs.",
            "severity":    "high",
            "instruction": "Take magnesium glycinate 200-400mg daily if on PPIs long-term. Get magnesium levels checked after 1 year of PPI use.",
            "source":      "FDA Drug Safety Communication",
            "evidence":    "strong",
        },
        {
            "nutrient":    "vitamin b12",
            "reason":      "PPIs reduce stomach acid which is required to absorb B12 from food.",
            "severity":    "moderate",
            "instruction": "Consider sublingual or methylcobalamin B12 which bypasses the need for stomach acid.",
            "source":      "Journal of the American Medical Association",
            "evidence":    "strong",
        },
        {
            "nutrient":    "calcium",
            "reason":      "PPIs reduce stomach acid needed to absorb calcium carbonate. Linked to increased fracture risk.",
            "severity":    "moderate",
            "instruction": "Use calcium citrate (not carbonate) which absorbs without stomach acid.",
            "source":      "Archives of Internal Medicine",
            "evidence":    "strong",
        },
        {
            "nutrient":    "iron",
            "reason":      "Stomach acid converts ferric iron to absorbable ferrous form. PPIs reduce this conversion.",
            "severity":    "moderate",
            "instruction": "Take iron with vitamin C to improve absorption. Consider iron levels if on PPIs long-term.",
            "source":      "Alimentary Pharmacology & Therapeutics",
            "evidence":    "moderate",
        },
    ],
    "esomeprazole":  "omeprazole",
    "pantoprazole":  "omeprazole",
    "lansoprazole":  "omeprazole",
    "levothyroxine": [
        {
            "nutrient":    "selenium",
            "reason":      "Selenium is required to convert T4 to active T3 thyroid hormone. Deficiency reduces thyroid medication effectiveness.",
            "severity":    "moderate",
            "instruction": "Ensure adequate selenium (55-200mcg/day). Brazil nuts (1-2/day) or a selenium supplement.",
            "source":      "Journal of Clinical Endocrinology",
            "evidence":    "moderate",
        },
        {
            "nutrient":    "zinc",
            "reason":      "Zinc is required for thyroid hormone synthesis and receptor activity.",
            "severity":    "moderate",
            "instruction": "Ensure adequate zinc (8-11mg/day). Zinc picolinate or citrate are well absorbed.",
            "source":      "Biological Trace Element Research",
            "evidence":    "moderate",
        },
    ],
    "furosemide": [
        {
            "nutrient":    "magnesium",
            "reason":      "Loop diuretics cause significant urinary magnesium wasting. Hypomagnesemia is common in patients on furosemide.",
            "severity":    "high",
            "instruction": "Magnesium supplementation (300-400mg/day) is often recommended with loop diuretics. Discuss with your doctor.",
            "source":      "American Journal of Medicine",
            "evidence":    "strong",
        },
        {
            "nutrient":    "potassium",
            "reason":      "Furosemide causes significant potassium loss in urine.",
            "severity":    "high",
            "instruction": "Potassium levels should be monitored regularly. Dietary potassium and/or supplementation may be needed.",
            "source":      "Journal of Clinical Pharmacology",
            "evidence":    "strong",
        },
        {
            "nutrient":    "zinc",
            "reason":      "Loop diuretics increase urinary zinc excretion.",
            "severity":    "moderate",
            "instruction": "Consider zinc supplementation (15-30mg/day) if on furosemide long-term.",
            "source":      "Nephron",
            "evidence":    "moderate",
        },
    ],
    "hydrochlorothiazide": [
        {
            "nutrient":    "magnesium",
            "reason":      "Thiazide diuretics cause urinary magnesium wasting.",
            "severity":    "moderate",
            "instruction": "Magnesium glycinate 200-400mg/day may help replace losses.",
            "source":      "Journal of Hypertension",
            "evidence":    "moderate",
        },
        {
            "nutrient":    "potassium",
            "reason":      "Thiazide diuretics increase urinary potassium excretion.",
            "severity":    "moderate",
            "instruction": "Monitor potassium levels. Dietary sources (bananas, avocado) or supplementation may be needed.",
            "source":      "Hypertension",
            "evidence":    "strong",
        },
        {
            "nutrient":    "zinc",
            "reason":      "Thiazide diuretics increase urinary zinc excretion.",
            "severity":    "moderate",
            "instruction": "Consider zinc supplementation if on thiazides long-term.",
            "source":      "Nephron",
            "evidence":    "moderate",
        },
    ],
    "prednisone": [
        {
            "nutrient":    "calcium",
            "reason":      "Long-term corticosteroid use reduces calcium absorption and increases urinary calcium loss, causing bone loss.",
            "severity":    "high",
            "instruction": "Calcium (1200mg/day) + Vitamin D3 (2000IU) is standard with long-term corticosteroids to prevent osteoporosis.",
            "source":      "American College of Rheumatology",
            "evidence":    "strong",
        },
        {
            "nutrient":    "vitamin d3",
            "reason":      "Corticosteroids reduce vitamin D activation and calcium absorption.",
            "severity":    "high",
            "instruction": "Vitamin D3 2000-4000 IU daily when on long-term corticosteroids.",
            "source":      "American College of Rheumatology",
            "evidence":    "strong",
        },
        {
            "nutrient":    "magnesium",
            "reason":      "Corticosteroids increase urinary magnesium excretion.",
            "severity":    "moderate",
            "instruction": "Magnesium 300-400mg/day to replace losses.",
            "source":      "Steroids Journal",
            "evidence":    "moderate",
        },
        {
            "nutrient":    "zinc",
            "reason":      "Corticosteroids increase zinc excretion and impair immune function.",
            "severity":    "moderate",
            "instruction": "Zinc 15-30mg/day to support immune function.",
            "source":      "Journal of Nutritional Biochemistry",
            "evidence":    "moderate",
        },
    ],
    "prednisolone":  "prednisone",
    "dexamethasone": "prednisone",
    "sertraline": [
        {
            "nutrient":    "magnesium",
            "reason":      "SSRIs can reduce magnesium levels. Magnesium also modulates serotonin receptors and has synergistic effects with antidepressants.",
            "severity":    "moderate",
            "instruction": "Magnesium glycinate 200-400mg at night supports mood and sleep. Discuss with prescriber.",
            "source":      "Pharmacological Reports",
            "evidence":    "moderate",
        },
    ],
    "fluoxetine":    "sertraline",
    "escitalopram":  "sertraline",
    "paroxetine":    "sertraline",
    "warfarin": [
        {
            "nutrient":    "vitamin d3",
            "reason":      "Patients on warfarin are often vitamin D deficient. Vitamin D deficiency may also affect warfarin sensitivity.",
            "severity":    "moderate",
            "instruction": "Vitamin D3 supplementation is generally safe with warfarin at standard doses (1000-2000 IU). Monitor INR when starting.",
            "source":      "Thrombosis Research",
            "evidence":    "moderate",
        },
    ],
    "methotrexate": [
        {
            "nutrient":    "folate",
            "reason":      "Methotrexate is a folate antagonist — it works by blocking folate metabolism. Folate supplementation reduces side effects without reducing efficacy.",
            "severity":    "high",
            "instruction": "Folic acid 1-5mg/day is standard with methotrexate to prevent side effects. Take on days you don't take methotrexate.",
            "source":      "Annals of the Rheumatic Diseases",
            "evidence":    "strong",
        },
    ],
    "lisinopril": [
        {
            "nutrient":    "zinc",
            "reason":      "ACE inhibitors chelate zinc and increase urinary zinc excretion over time.",
            "severity":    "moderate",
            "instruction": "Consider zinc 15-30mg/day if on ACE inhibitors long-term.",
            "source":      "Journal of the American College of Nutrition",
            "evidence":    "moderate",
        },
    ],
    "enalapril":  "lisinopril",
    "ramipril":   "lisinopril",
    "amlodipine": [
        {
            "nutrient":    "coq10",
            "reason":      "Calcium channel blockers may reduce CoQ10 levels and CoQ10 may enhance their blood pressure lowering effects.",
            "severity":    "moderate",
            "instruction": "CoQ10 100mg/day may complement blood pressure management and offset potential depletion.",
            "source":      "Molecular Aspects of Medicine",
            "evidence":    "moderate",
        },
    ],
    "phenytoin": [
        {
            "nutrient":    "vitamin d3",
            "reason":      "Phenytoin induces liver enzymes that break down vitamin D, causing deficiency and bone loss.",
            "severity":    "high",
            "instruction": "Vitamin D3 2000-4000 IU daily. Bone density monitoring recommended with long-term use.",
            "source":      "Epilepsia",
            "evidence":    "strong",
        },
        {
            "nutrient":    "folate",
            "reason":      "Phenytoin reduces folate absorption and increases folate metabolism.",
            "severity":    "high",
            "instruction": "Folate supplementation (1mg/day) with phenytoin. Note: high-dose folate may reduce phenytoin levels.",
            "source":      "Neurology",
            "evidence":    "strong",
        },
        {
            "nutrient":    "calcium",
            "reason":      "Phenytoin reduces calcium absorption by reducing vitamin D levels.",
            "severity":    "moderate",
            "instruction": "Calcium 1000-1200mg/day alongside vitamin D supplementation.",
            "source":      "Epilepsia",
            "evidence":    "moderate",
        },
    ],
    "carbamazepine": [
        {
            "nutrient":    "vitamin d3",
            "reason":      "Carbamazepine induces CYP enzymes that break down vitamin D.",
            "severity":    "high",
            "instruction": "Vitamin D3 2000-4000 IU daily. Monitor vitamin D levels.",
            "source":      "Epilepsia",
            "evidence":    "strong",
        },
        {
            "nutrient":    "folate",
            "reason":      "Carbamazepine reduces folate absorption.",
            "severity":    "moderate",
            "instruction": "Folate 1mg/day recommended with carbamazepine.",
            "source":      "Neurology",
            "evidence":    "moderate",
        },
    ],
    "isoniazid": [
        {
            "nutrient":    "vitamin b6",
            "reason":      "Isoniazid inhibits the enzyme that activates B6 (pyridoxal kinase), causing B6 deficiency and peripheral neuropathy.",
            "severity":    "high",
            "instruction": "Vitamin B6 (pyridoxine) 25-50mg/day is standard with isoniazid to prevent neuropathy.",
            "source":      "American Thoracic Society",
            "evidence":    "strong",
        },
    ],
    "digoxin": [
        {
            "nutrient":    "magnesium",
            "reason":      "Magnesium deficiency increases digoxin toxicity risk. Hypomagnesemia sensitizes the heart to digoxin.",
            "severity":    "high",
            "instruction": "Maintain adequate magnesium levels when on digoxin. Magnesium deficiency is dangerous with this medication.",
            "source":      "American Journal of Cardiology",
            "evidence":    "strong",
        },
    ],
}

DRUG_CLASS_GAPS = {
    "statin":         ["coq10"],
    "ppi":            ["magnesium", "vitamin b12", "calcium", "iron"],
    "diuretic":       ["magnesium", "potassium", "zinc"],
    "corticosteroid": ["calcium", "vitamin d3", "magnesium", "zinc"],
    "ssri":           ["magnesium"],
    "ace inhibitor":  ["zinc"],
    "anticonvulsant": ["vitamin d3", "folate", "calcium"],
}


def detect_gaps(
    medications: list[str],
    supplements: list[str],
) -> list[dict]:
    """
    Detect nutrients depleted by medications but missing from the supplement stack.
    """
    if not medications:
        return []

    supps_lower = [s.lower().strip() for s in supplements]
    gaps        = []
    seen        = set()

    for med in medications:
        med_lower = med.lower().strip()

        gaps_for_med = MEDICATION_GAPS.get(med_lower)

        if isinstance(gaps_for_med, str):
            gaps_for_med = MEDICATION_GAPS.get(gaps_for_med, [])

        if not gaps_for_med:
            for known_drug in MEDICATION_GAPS:
                if known_drug in med_lower or med_lower in known_drug:
                    gaps_for_med = MEDICATION_GAPS[known_drug]
                    if isinstance(gaps_for_med, str):
                        gaps_for_med = MEDICATION_GAPS.get(gaps_for_med, [])
                    break

        if not gaps_for_med:
            continue

        for gap in gaps_for_med:
            nutrient    = gap["nutrient"].lower()
            gap_key     = f"{med_lower}:{nutrient}"

            if gap_key in seen:
                continue

            nutrient_covered = False
            nutrient_words   = set(nutrient.split())

            for supp in supps_lower:
                supp_words = set(supp.split())
                overlap = nutrient_words & supp_words
                if overlap and len(overlap) >= min(1, len(nutrient_words) - 1):
                    nutrient_covered = True
                    break
                if nutrient in supp or any(w in supp for w in nutrient_words if len(w) > 3):
                    nutrient_covered = True
                    break

            if not nutrient_covered:
                seen.add(gap_key)
                gaps.append({
                    **gap,
                    "medication": med,
                    "gap_type":   "drug_depletion",
                    "check_type": "gap_detection",
                })

    severity_order = {"high": 0, "moderate": 1, "low": 2}
    gaps.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 2))

    return gaps[:5]


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get_json(url: str, timeout: int = 6) -> Any:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Elthio/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug("GET %s failed: %s", url, e)
        return None


# ── 1. RxNorm ─────────────────────────────────────────────────────────────────
def resolve_with_rxnorm(query: str) -> list[dict]:
    """Authoritative NIH drug name resolution. No API key required."""
    data = _get_json(
        f"https://rxnav.nlm.nih.gov/REST/drugs.json"
        f"?name={urllib.parse.quote(query)}"
    )
    if not data:
        return []
    results = []
    for group in data.get("drugGroup", {}).get("conceptGroup", []):
        if group.get("tty") not in ("IN", "BN", "PIN", "MIN", "SCD"):
            continue
        for prop in group.get("conceptProperties", []):
            results.append({
                "rxcui": prop.get("rxcui", ""),
                "name":  prop.get("name", ""),
                "tty":   group.get("tty", ""),
            })
    return results[:5]


def rxnorm_synonyms(rxcui: str) -> list[str]:
    data = _get_json(
        f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=BN+IN+PIN"
    )
    if not data:
        return []
    names = []
    for group in data.get("relatedGroup", {}).get("conceptGroup", []):
        for prop in group.get("conceptProperties", []):
            if prop.get("name"):
                names.append(prop["name"].lower())
    return names[:10]


# ── 2. OpenFDA deep pull ──────────────────────────────────────────────────────
def query_openfda(drug_name: str) -> list[dict]:
    """Pull all 6 FDA label fields, filter for supplement-relevant content."""
    encoded = urllib.parse.quote(drug_name)
    data = _get_json(
        f"{OPENFDA_BASE}?search=openfda.generic_name:{encoded}"
        f"+OR+openfda.brand_name:{encoded}&limit=1"
    )
    if not data or not data.get("results"):
        return []
    label     = data["results"][0]
    extracted = []
    for field in OPENFDA_SUPPLEMENT_FIELDS:
        raw = label.get(field)
        if not raw:
            continue
        text = raw[0] if isinstance(raw, list) else str(raw)
        if not any(kw in text.lower() for kw in SUPPLEMENT_KEYWORDS):
            continue
        sentences = [
            s.strip() for s in text.replace("\n", " ").split(".")
            if any(kw in s.lower() for kw in SUPPLEMENT_KEYWORDS)
            and len(s.strip()) > 20
        ]
        if sentences:
            extracted.append({
                "field":  field,
                "text":   ". ".join(sentences[:3]) + ".",
                "source": "FDA drug label",
            })
    return extracted


# ── 3. PubChem ────────────────────────────────────────────────────────────────
def get_pubchem_context(supplement_name: str) -> dict:
    """Supplement compound data from NIH PubChem. No API key required."""
    encoded  = urllib.parse.quote(supplement_name)
    cid_data = _get_json(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug"
        f"/compound/name/{encoded}/cids/JSON?name_type=word"
    )
    if not cid_data:
        return {}
    cids = cid_data.get("IdentifierList", {}).get("CID", [])
    if not cids:
        return {}
    cid       = cids[0]
    props_raw = _get_json(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}"
        f"/property/MolecularFormula,IUPACName,MolecularWeight/JSON"
    )
    props = {}
    if props_raw:
        p     = props_raw.get("PropertyTable", {}).get("Properties", [{}])[0]
        props = {
            "formula": p.get("MolecularFormula", ""),
            "weight":  p.get("MolecularWeight", ""),
            "name":    p.get("IUPACName", supplement_name),
        }
    bio_data = _get_json(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
        f"/data/compound/{cid}/JSON?heading=Biological+Activities"
    )
    bio_text = ""
    if bio_data:
        for section in bio_data.get("Record", {}).get("Section", []):
            for item in section.get("Information", [])[:2]:
                for s in item.get("Value", {}).get("StringWithMarkup", [])[:1]:
                    bio_text += s.get("String", "") + " "
    return {"cid": cid, "bio_activity": bio_text.strip()[:400],
            "source": f"PubChem CID {cid}", **props}


# ── 4. MedlinePlus ────────────────────────────────────────────────────────────
def get_medlineplus(drug_name: str) -> dict:
    """NIH MedlinePlus plain-English drug summaries. No API key required."""
    encoded = urllib.parse.quote(drug_name)
    data    = _get_json(
        f"https://connect.medlineplus.gov/application"
        f"?mainSearchCriteria.v.cs=2.16.840.1.113883.6.88"
        f"&mainSearchCriteria.v.dn={encoded}"
        f"&knowledgeResponseType=application/json"
    )
    if not data:
        return {}
    entries = data.get("feed", {}).get("entry", [])
    if not entries:
        return {}
    entry   = entries[0]
    title   = entry.get("title", {})
    summary = entry.get("summary", {})
    link    = entry.get("link", [{}])
    return {
        "title":   title.get("_value", "") if isinstance(title, dict) else str(title),
        "summary": (summary.get("_value", "") if isinstance(summary, dict) else str(summary))[:400],
        "url":     link[0].get("href", "") if isinstance(link, list) and link else "",
        "source":  "NIH MedlinePlus",
    }


# ── 5. Claude helper ──────────────────────────────────────────────────────────
def call_claude(messages: list[dict], system: str, max_tokens: int = 1024) -> str:
    key = _anthropic_key()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    if not key.startswith("sk-ant"):
        raise ValueError("ANTHROPIC_API_KEY must start with sk-ant-")
    payload = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   messages,
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        log.warning("Claude HTTP %s: %s", e.code, body)
        raise ValueError(f"Claude API error {e.code}: {body}") from e


# ── 6. Intent resolver ────────────────────────────────────────────────────────
def resolve_intent(query: str) -> dict:
    """RxNorm + phrase dict + Claude fallback for maximum name resolution."""
    query_lower = query.lower()

    # Phase 1: phrase dictionary (instant)
    pre_resolved = []
    for phrase, drugs in COMMON_RESOLUTIONS.items():
        if phrase in query_lower:
            pre_resolved.extend(drugs)

    # Phase 1b: supplement phrase dictionary (instant, no Claude)
    phrase_supps = []
    for phrase in sorted(COMMON_SUPPLEMENT_PHRASES, key=len, reverse=True):
        if phrase in query_lower and phrase not in phrase_supps:
            phrase_supps.append(phrase)

    # Phase 2: RxNorm for individual words
    skip_words = {
        "taking", "bought", "started", "using", "want", "trying",
        "supplement", "vitamin", "mineral", "herbal", "natural",
        "daily", "every", "since", "with", "and", "my",
    }
    rxnorm_resolved = []
    for word in query_lower.split():
        word = word.strip(".,?")
        if len(word) > 5 and word not in skip_words:
            hits = resolve_with_rxnorm(word)
            if hits:
                name = hits[0]["name"].lower()
                if name not in pre_resolved:
                    rxnorm_resolved.append(name)
                    log.info("RxNorm: '%s' → '%s'", word, name)

    # Phase 3: Claude for supplements and ambiguous terms
    system = """Medical terminology resolver for a supplement safety app.
Extract medications and supplements from the query.
Return ONLY valid JSON — no markdown fences, no explanation:
{"medications":["generic name"],"supplements":["supplement name"],"confidence":"high|medium|low","notes":""}
Rules: use generic names, keep supplements specific, return empty arrays if nothing found."""

    ai_meds, ai_supps, confidence, notes = [], [], "medium", ""
    try:
        raw    = call_claude(
            [{"role": "user", "content": f"Extract from: {query}"}], system, 256
        )
        clean  = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        parsed = json.loads(clean)
        ai_meds    = [m.lower() for m in parsed.get("medications", [])]
        ai_supps   = [s.lower() for s in parsed.get("supplements", [])]
        confidence = parsed.get("confidence", "medium")
        notes      = parsed.get("notes", "")
    except Exception as e:
        log.warning("Claude entity extraction failed: %s", e)

    all_meds  = list(dict.fromkeys(pre_resolved + rxnorm_resolved + ai_meds))
    all_supps = list(dict.fromkeys(phrase_supps + ai_supps))
    return {
        "original_query":  query,
        "medications":     all_meds,
        "supplements":     all_supps,
        "confidence":      confidence,
        "notes":           notes,
        "rxnorm_resolved": rxnorm_resolved,
        "phrase_resolved": pre_resolved,
        "phrase_supplements": phrase_supps,
    }


# ── 7. Main function ──────────────────────────────────────────────────────────
def ai_med_check(
    query: str,
    explicit_meds:  list[str] | None = None,
    explicit_supps: list[str] | None = None,
    email: str = "",
) -> dict[str, Any]:
    """
    Full AI Med Check pipeline.
    Accepts natural language query + optional explicit med/supp lists from UI.
    """
    from med_check_engine import run_med_check

    intent      = resolve_intent(query)
    medications = list(dict.fromkeys((explicit_meds or []) + intent.get("medications", [])))
    supplements = list(dict.fromkeys((explicit_supps or []) + intent.get("supplements", [])))

    memory_context = ""
    stack_changes  = {}
    try:
        from memory import build_memory_context, detect_stack_changes
        if email:
            memory_context = build_memory_context(email)
            stack_changes  = detect_stack_changes(email, medications, supplements)
            log.info("Memory context loaded for %s (%d chars)",
                     email, len(memory_context))
    except Exception as e:
        log.warning("Memory load failed: %s", e)

    def _with_memory(prompt: str) -> str:
        if memory_context:
            prompt = (
                f"RETURNING USER CONTEXT:\n{memory_context}\n\n"
                f"CURRENT SESSION:\n{prompt}"
            )
        if stack_changes.get("has_changes"):
            added_s   = stack_changes.get("added_supps",  [])
            removed_s = stack_changes.get("removed_supps", [])
            added_m   = stack_changes.get("added_meds",   [])
            if added_s or added_m or removed_s:
                change_note = "STACK CHANGES SINCE LAST VISIT: "
                if added_m:
                    change_note += f"New medications: {', '.join(added_m)}. "
                if added_s:
                    change_note += f"New supplements: {', '.join(added_s)}. "
                if removed_s:
                    change_note += f"Removed: {', '.join(removed_s)}. "
                prompt = change_note + "\n\n" + prompt
        return prompt

    if not medications and not supplements:
        return {
            "query": query, "intent": intent,
            "interactions": [], "near_misses": [],
            "explanation": (
                "I couldn't identify specific medications or supplements. "
                "Try: 'warfarin and vitamin K2' or "
                "'I take levothyroxine and want to start magnesium'."
            ),
            "ai_enhanced": True, "rules_checked": 0,
            "gaps": [], "gap_count": 0,
        }

    if query.strip().lower() == "__gaps_only__":
        gaps = detect_gaps(medications, supplements)
        return {
            "query":                query,
            "intent":               intent,
            "resolved_medications": medications,
            "resolved_supplements": supplements,
            "gaps":                 gaps,
            "gap_count":            len(gaps),
            "interactions":         [],
            "synergies":            [],
            "near_misses":          [],
            "explanation":          "",
            "ai_enhanced":          False,
            "rules_checked":        0,
        }

    # RxNorm live drug resolution + FDA interaction data
    rxnorm_context: dict[str, Any] = {}
    try:
        from rxnorm import get_rxnorm_context
        rxnorm_context = get_rxnorm_context(medications, supplements)
        if rxnorm_context.get("resolved_meds"):
            log.info(
                "RxNorm: resolved %d meds, %d FDA interactions",
                len(rxnorm_context["resolved_meds"]),
                len(rxnorm_context["drug_interactions"]),
            )
    except Exception as e:
        log.warning("RxNorm lookup failed: %s", e)

    normalized_meds = []
    for med in medications:
        resolved = rxnorm_context.get("resolved_meds", {}).get(med)
        if resolved and resolved.get("name"):
            normalized_meds.append(resolved["name"])
        else:
            normalized_meds.append(med)

    # Hybrid vector + keyword search
    try:
        from vector_search import hybrid_search
        result = hybrid_search(normalized_meds, supplements)
        result["supp_interactions"] = [
            i for i in result.get("interactions", [])
            if i.get("check_type") == "supplement_supplement"
            or i.get("_rule_type") == "supplement_supplement"
        ]
        result["supp_synergies"] = result.get("synergies", [])
    except Exception as e:
        log.warning("Hybrid search unavailable, using keyword: %s", e)
        from med_check_engine import run_med_check
        result = run_med_check(normalized_meds, supplements, [])
    interactions = result.get("interactions", [])
    near_misses  = result.get("near_misses", [])

    # FAERS adverse event data
    faers_context = []
    try:
        from faers import get_faers_context_for_stack
        faers_context = get_faers_context_for_stack(normalized_meds, supplements)
        log.info("FAERS: %d pairs with adverse events", len(faers_context))
    except Exception as e:
        log.warning("FAERS lookup failed: %s", e)

    # Parallel API enrichment
    openfda_data, pubchem_data, medlineplus_data = [], [], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        fda_futs = {ex.submit(query_openfda, m): m        for m in normalized_meds[:2]}
        pub_futs = {ex.submit(get_pubchem_context, s): s  for s in supplements[:2]}
        mpl_futs = {ex.submit(get_medlineplus, m): m      for m in normalized_meds[:1]}

        for f in concurrent.futures.as_completed(fda_futs):
            try:
                d = f.result()
                if d: openfda_data.extend(d)
            except Exception as e:
                log.warning("OpenFDA error: %s", e)

        for f in concurrent.futures.as_completed(pub_futs):
            try:
                d = f.result()
                if d: pubchem_data.append(d)
            except Exception as e:
                log.warning("PubChem error: %s", e)

        for f in concurrent.futures.as_completed(mpl_futs):
            try:
                d = f.result()
                if d: medlineplus_data.append(d)
            except Exception as e:
                log.warning("MedlinePlus error: %s", e)

    # Build context block for Claude explanations
    ctx = ""
    if rxnorm_context.get("context_text"):
        ctx += rxnorm_context["context_text"] + "\n"
    if openfda_data:
        ctx += "\nFDA Label Data:\n" + "".join(
            f"- {d['field']}: {d['text'][:200]}\n" for d in openfda_data[:3]
        )
    if pubchem_data:
        ctx += "\nPubChem Chemistry:\n" + "".join(
            f"- {d.get('name','')}: {d.get('bio_activity','')[:200]}\n"
            for d in pubchem_data[:2] if d.get("bio_activity")
        )
    if medlineplus_data:
        ctx += "\nNIH MedlinePlus:\n" + "".join(
            f"- {d.get('summary','')[:200]}\n" for d in medlineplus_data[:1]
        )
    if faers_context:
        faers_summary = "FDA ADVERSE EVENT DATA (real-world reports):\n"
        for pair in faers_context[:3]:
            f = pair["faers"]
            faers_summary += (
                f"- {pair['drug']} + {pair['supplement']}: "
                f"{f['total_events']} total reports, "
                f"{f['serious_count']} serious, "
                f"{f['death_count']} deaths reported\n"
                f"  Top reactions: "
                f"{', '.join(r['reaction'] for r in f['top_reactions'][:5])}\n"
            )
        ctx += "\n" + faers_summary

    synergies = result.get("synergies") or []
    if synergies:
        syn_text = "SUPPLEMENT SYNERGIES (beneficial combinations):\n"
        for s in synergies[:3]:
            syn_text += (
                f"- {s['supplement_a']} + {s['supplement_b']}: "
                f"{s['title']} — {s['detail'][:120]}\n"
            )
        ctx += "\n" + syn_text

    timing_conflicts = result.get("timing_conflicts") or []
    if timing_conflicts:
        tim_text = "TIMING CONFLICTS (take separately):\n"
        for t in timing_conflicts[:3]:
            tim_text += (
                f"- {t['supplement_a']} + {t['supplement_b']}: "
                f"separate by {t.get('timing_hours', 2)} hours — "
                f"{t['instruction'][:100]}\n"
            )
        ctx += "\n" + tim_text

    gaps = []
    try:
        gaps = detect_gaps(normalized_meds, supplements)
        if gaps:
            gap_text = "NUTRIENT GAPS DETECTED (medications depleting nutrients not in stack):\n"
            for g in gaps:
                gap_text += (
                    f"- {g['medication']} depletes {g['nutrient']}: "
                    f"{g['reason'][:100]}. "
                    f"Instruction: {g['instruction'][:100]}\n"
                )
            ctx += "\n" + gap_text
            log.info("Gap detection: %d gaps found", len(gaps))
    except Exception as e:
        log.warning("Gap detection error: %s", e)

    gap_prompt_lines = (
        "- If nutrient gaps are provided, mention the most important one naturally\n"
        "- Frame gaps as helpful insights not warnings: 'You might want to consider...'\n"
        "- Only mention gaps if they are HIGH severity or there are 2+ moderate ones\n"
        "- Never list more than 2 gap suggestions in one response\n"
        "- Gap suggestions should feel like a knowledgeable friend noticing something\n"
        "  not a clinical recommendation\n"
    )

    # Enhance each interaction with Claude explanation
    explain_system = """You are a pharmacist assistant for Elthio.
Explain drug-supplement interactions clearly. 2-3 short paragraphs.
Plain English. Always end with 'discuss with your pharmacist or doctor'.
Never say definitely safe or definitely dangerous.
- If synergies are present, mention them positively — these are good combinations
- If timing conflicts exist, clearly state what needs to be separated and by how long
- Distinguish between drug-supplement interactions (safety) and supplement-supplement interactions (optimization)
""" + gap_prompt_lines

    enhanced = []
    claude_calls = 0
    claude_ok = 0
    claude_error = ""

    for ix in interactions:
        med_name  = normalized_meds[0]  if normalized_meds  else ""
        supp_name = supplements[0] if supplements else ""
        prompt    = (
            f'User asked: "{query}"\n\n'
            f"Interaction: {ix.get('severity')} — {ix.get('title')}\n"
            f"Detail: {ix.get('detail','')}\n"
            f"Instruction: {ix.get('instruction','')}\n"
            f"Source: {ix.get('source','')}\n{ctx}\n\n"
            f"Explain for {med_name} + {supp_name}."
        )
        expl = ix.get("instruction", "") or ix.get("detail", "")
        try:
            claude_calls += 1
            expl = call_claude(
                [{"role": "user", "content": _with_memory(prompt)}],
                explain_system,
            )
            if len(expl.strip()) > len((ix.get("instruction") or "").strip()) + 30:
                claude_ok += 1
        except Exception as e:
            if not claude_error:
                claude_error = str(e)
            log.warning("Claude explanation failed: %s", e)
        enhanced.append({**ix, "ai_explanation": expl})

    # Overall explanation
    no_match_system = """Pharmacist assistant for Elthio.
Combination not in our database. Use FDA/PubChem data provided.
2 short paragraphs. Never invent interactions. Recommend pharmacist consultation.
""" + gap_prompt_lines
    match_system = """Pharmacist assistant for Elthio.
Summarize the interaction findings for the user in 2 short paragraphs.
Plain English. Always end with 'discuss with your pharmacist or doctor'.
- If synergies are present, mention them positively — these are good combinations
- If timing conflicts exist, clearly state what needs to be separated and by how long
- Distinguish between drug-supplement interactions (safety) and supplement-supplement interactions (optimization)
""" + gap_prompt_lines

    if not interactions:
        prompt = (
            f'User asked: "{query}"\n'
            f"Medications: {normalized_meds}\nSupplements: {supplements}\n"
            f"Database: no specific rule found.\n{ctx}\n\nProvide a helpful response."
        )
        overall = (
            "This combination isn't in our current database. "
            "That doesn't mean it's safe — please consult your pharmacist."
        )
        try:
            claude_calls += 1
            overall = call_claude(
                [{"role": "user", "content": _with_memory(prompt)}],
                no_match_system,
            )
            claude_ok += 1
        except Exception as e:
            if not claude_error:
                claude_error = str(e)
            log.warning("Claude no-match explanation failed: %s", e)
    else:
        sevs = [i.get("severity") for i in interactions]
        overall = (
            f"Found {len(interactions)} critical interaction(s). Review carefully and speak with your pharmacist."
            if "critical" in sevs else
            f"Found {len(interactions)} interaction(s) to be aware of. Manageable with the right timing and monitoring."
        )
        prompt = (
            f'User asked: "{query}"\n'
            f"Medications: {normalized_meds}\nSupplements: {supplements}\n"
            f"Interactions found: {len(interactions)}\n"
            f"Top concern: {interactions[0].get('title')} ({interactions[0].get('severity')})\n"
            f"{ctx}\n\nProvide a brief overall summary."
        )
        try:
            claude_calls += 1
            overall = call_claude(
                [{"role": "user", "content": _with_memory(prompt)}],
                match_system,
            )
            claude_ok += 1
        except Exception as e:
            if not claude_error:
                claude_error = str(e)
            log.warning("Claude overall summary failed: %s", e)

    sources = set()
    for i in interactions:
        if i.get("source"): sources.add(i["source"])
    if openfda_data:     sources.add("FDA Drug Label (OpenFDA)")
    if pubchem_data:     sources.add(f"PubChem CID {pubchem_data[0].get('cid','')}")
    if medlineplus_data: sources.add("NIH MedlinePlus")
    if faers_context:    sources.add("FDA FAERS (OpenFDA adverse events)")
    if rxnorm_context.get("drug_interactions"):
        sources.add("NLM RxNav Drug Interaction API")
    sources.add("Educational only — not medical advice. Consult your pharmacist.")

    out = {
        "query":                query,
        "intent":               intent,
        "resolved_medications": normalized_meds,
        "resolved_supplements": supplements,
        "rxnorm_resolved":      rxnorm_context.get("resolved_meds", {}),
        "fda_interactions":     rxnorm_context.get("drug_interactions", []),
        "rxcui_list":           rxnorm_context.get("rxcui_list", []),
        "interactions":         enhanced,
        "near_misses":          near_misses,
        "openfda_data":         openfda_data,
        "pubchem_data":         pubchem_data,
        "medlineplus_data":     medlineplus_data,
        "faers_context":        faers_context,
        "explanation":          overall,
        "sources":              list(sources),
        "ai_enhanced":          claude_ok > 0,
        "ai_status": {
            "claude_configured": claude_configured(),
            "claude_calls":      claude_calls,
            "claude_ok":         claude_ok,
            "claude_error":      claude_error or None,
        },
        "rules_checked":        result.get("rules_checked", 0),
        "synergies":            synergies,
        "timing_conflicts":     timing_conflicts,
        "supp_interactions":    result.get("supp_interactions", []),
        "supp_synergies":       result.get("supp_synergies", []),
        "memory_context_used":  bool(memory_context),
        "stack_changes":        stack_changes,
        "gaps":                 gaps,
        "gap_count":            len(gaps),
    }

    if email:
        try:
            from memory import save_session
            save_session(
                email            = email,
                medications      = normalized_meds,
                supplements      = supplements,
                med_check_result = {
                    "interactions": interactions,
                    "synergies":    synergies,
                },
                safety_score     = None,
            )
        except Exception as e:
            log.warning("Session save failed: %s", e)

    return out


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    tests = [
        ("RxNorm resolve",         lambda: resolve_with_rxnorm("warfarin")),
        ("OpenFDA deep pull",      lambda: query_openfda("warfarin")),
        ("PubChem ashwagandha",    lambda: get_pubchem_context("ashwagandha")),
        ("MedlinePlus warfarin",   lambda: get_medlineplus("warfarin")),
        ("Blood thinner + turmeric", lambda: ai_med_check("I take a blood thinner and just bought turmeric")),
        ("Thyroid + magnesium",    lambda: ai_med_check("Can I take magnesium with my thyroid medication?")),
    ]
    passed = 0
    for name, fn in tests:
        try:
            r = fn()
            print(f"  ✅ {name}: OK — {str(r)[:80]}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: FAILED — {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
    if not claude_configured():
        print("⚠  Set ANTHROPIC_API_KEY (sk-ant-...) to enable Claude explanations")
