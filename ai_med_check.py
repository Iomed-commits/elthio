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
) -> dict[str, Any]:
    """
    Full AI Med Check pipeline.
    Accepts natural language query + optional explicit med/supp lists from UI.
    """
    from med_check_engine import run_med_check

    intent      = resolve_intent(query)
    medications = list(dict.fromkeys((explicit_meds or []) + intent.get("medications", [])))
    supplements = list(dict.fromkeys((explicit_supps or []) + intent.get("supplements", [])))

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
        }

    # Check local 114-rule DB
    result       = run_med_check(medications, supplements, [])
    interactions = result.get("interactions", [])
    near_misses  = result.get("near_misses", [])

    # Parallel API enrichment
    openfda_data, pubchem_data, medlineplus_data = [], [], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        fda_futs = {ex.submit(query_openfda, m): m        for m in medications[:2]}
        pub_futs = {ex.submit(get_pubchem_context, s): s  for s in supplements[:2]}
        mpl_futs = {ex.submit(get_medlineplus, m): m      for m in medications[:1]}

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

    # Enhance each interaction with Claude explanation
    explain_system = """You are a pharmacist assistant for Elthio.
Explain drug-supplement interactions clearly. 2-3 short paragraphs.
Plain English. Always end with 'discuss with your pharmacist or doctor'.
Never say definitely safe or definitely dangerous."""

    enhanced = []
    claude_calls = 0
    claude_ok = 0
    claude_error = ""

    for ix in interactions:
        med_name  = medications[0]  if medications  else ""
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
            expl = call_claude([{"role": "user", "content": prompt}], explain_system)
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
2 short paragraphs. Never invent interactions. Recommend pharmacist consultation."""
    match_system = """Pharmacist assistant for Elthio.
Summarize the interaction findings for the user in 2 short paragraphs.
Plain English. Always end with 'discuss with your pharmacist or doctor'."""

    if not interactions:
        prompt = (
            f'User asked: "{query}"\n'
            f"Medications: {medications}\nSupplements: {supplements}\n"
            f"Database: no specific rule found.\n{ctx}\n\nProvide a helpful response."
        )
        overall = (
            "This combination isn't in our current database. "
            "That doesn't mean it's safe — please consult your pharmacist."
        )
        try:
            claude_calls += 1
            overall = call_claude([{"role": "user", "content": prompt}], no_match_system)
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
            f"Medications: {medications}\nSupplements: {supplements}\n"
            f"Interactions found: {len(interactions)}\n"
            f"Top concern: {interactions[0].get('title')} ({interactions[0].get('severity')})\n"
            f"{ctx}\n\nProvide a brief overall summary."
        )
        try:
            claude_calls += 1
            overall = call_claude([{"role": "user", "content": prompt}], match_system)
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
    sources.add("Educational only — not medical advice. Consult your pharmacist.")

    return {
        "query":                query,
        "intent":               intent,
        "resolved_medications": medications,
        "resolved_supplements": supplements,
        "rxnorm_resolved":      intent.get("rxnorm_resolved", []),
        "interactions":         enhanced,
        "near_misses":          near_misses,
        "openfda_data":         openfda_data,
        "pubchem_data":         pubchem_data,
        "medlineplus_data":     medlineplus_data,
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
    }


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
