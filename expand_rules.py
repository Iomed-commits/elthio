"""
expand_rules.py — Automated NIH ODS rule expansion

Fetches NIH Office of Dietary Supplements fact sheets for 50+
supplements, uses Claude to extract every drug interaction mentioned,
formats them into Elthio's rule schema, deduplicates against existing
rules, and merges into interactions_db.json.

Run:     python expand_rules.py
Preview: python expand_rules.py --dry-run
Single:  python expand_rules.py --supplement "vitamin d"
Status:  python expand_rules.py --status
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-sonnet-4-5-20250929"

INTERACTIONS_DB   = Path(__file__).parent / "interactions_db.json"
EXPANDED_DB       = Path(__file__).parent / "expanded_rules.json"
BACKUP_DB         = Path(__file__).parent / "interactions_db_backup.json"

NIH_ODS_SUPPLEMENTS = {
    "vitamin_d":        "https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/",
    "magnesium":        "https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/",
    "calcium":          "https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/",
    "zinc":             "https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/",
    "iron":             "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
    "vitamin_c":        "https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/",
    "vitamin_e":        "https://ods.od.nih.gov/factsheets/VitaminE-HealthProfessional/",
    "vitamin_k":        "https://ods.od.nih.gov/factsheets/VitaminK-HealthProfessional/",
    "vitamin_b12":      "https://ods.od.nih.gov/factsheets/VitaminB12-HealthProfessional/",
    "folate":           "https://ods.od.nih.gov/factsheets/Folate-HealthProfessional/",
    "vitamin_b6":       "https://ods.od.nih.gov/factsheets/VitaminB6-HealthProfessional/",
    "vitamin_a":        "https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/",
    "omega3":           "https://ods.od.nih.gov/factsheets/Omega3FattyAcids-HealthProfessional/",
    "coq10":            "https://ods.od.nih.gov/factsheets/Coenzyme_Q10-HealthProfessional/",
    "melatonin":        "https://ods.od.nih.gov/factsheets/Melatonin-HealthProfessional/",
    "probiotics":       "https://ods.od.nih.gov/factsheets/Probiotics-HealthProfessional/",
    "selenium":         "https://ods.od.nih.gov/factsheets/Selenium-HealthProfessional/",
    "iodine":           "https://ods.od.nih.gov/factsheets/Iodine-HealthProfessional/",
    "copper":           "https://ods.od.nih.gov/factsheets/Copper-HealthProfessional/",
    "chromium":         "https://ods.od.nih.gov/factsheets/Chromium-HealthProfessional/",
    "potassium":        "https://ods.od.nih.gov/factsheets/Potassium-HealthProfessional/",
    "phosphorus":       "https://ods.od.nih.gov/factsheets/Phosphorus-HealthProfessional/",
    "manganese":        "https://ods.od.nih.gov/factsheets/Manganese-HealthProfessional/",
    "boron":            "https://ods.od.nih.gov/factsheets/Boron-HealthProfessional/",
    "niacin":           "https://ods.od.nih.gov/factsheets/Niacin-HealthProfessional/",
    "riboflavin":       "https://ods.od.nih.gov/factsheets/Riboflavin-HealthProfessional/",
    "thiamin":          "https://ods.od.nih.gov/factsheets/Thiamin-HealthProfessional/",
    "pantothenic_acid": "https://ods.od.nih.gov/factsheets/PantothenicAcid-HealthProfessional/",
    "biotin":           "https://ods.od.nih.gov/factsheets/Biotin-HealthProfessional/",
    "choline":          "https://ods.od.nih.gov/factsheets/Choline-HealthProfessional/",
    "carnitine":        "https://ods.od.nih.gov/factsheets/Carnitine-HealthProfessional/",
    "ashwagandha":      "https://ods.od.nih.gov/factsheets/Ashwagandha-HealthProfessional/",
    "berberine":        "https://ods.od.nih.gov/factsheets/Berberine-HealthProfessional/",
    "black_cohosh":     "https://ods.od.nih.gov/factsheets/Blackcohosh-HealthProfessional/",
    "cranberry":        "https://ods.od.nih.gov/factsheets/Cranberry-HealthProfessional/",
    "echinacea":        "https://ods.od.nih.gov/factsheets/Echinacea-HealthProfessional/",
    "evening_primrose": "https://ods.od.nih.gov/factsheets/Eveningprimroseoil-HealthProfessional/",
    "fenugreek":        "https://ods.od.nih.gov/factsheets/Fenugreek-HealthProfessional/",
    "garlic":           "https://ods.od.nih.gov/factsheets/Garlic-HealthProfessional/",
    "ginger":           "https://ods.od.nih.gov/factsheets/Ginger-HealthProfessional/",
    "ginkgo":           "https://ods.od.nih.gov/factsheets/Ginkgo-HealthProfessional/",
    "ginseng":          "https://ods.od.nih.gov/factsheets/AsianGinseng-HealthProfessional/",
    "glucosamine":      "https://ods.od.nih.gov/factsheets/Glucosamine-HealthProfessional/",
    "kava":             "https://ods.od.nih.gov/factsheets/Kava-HealthProfessional/",
    "licorice":         "https://ods.od.nih.gov/factsheets/Licoriceroot-HealthProfessional/",
    "milk_thistle":     "https://ods.od.nih.gov/factsheets/Milkthistle-HealthProfessional/",
    "peppermint":       "https://ods.od.nih.gov/factsheets/Peppermint-HealthProfessional/",
    "red_clover":       "https://ods.od.nih.gov/factsheets/Redclover-HealthProfessional/",
    "st_johns_wort":    "https://ods.od.nih.gov/factsheets/Stjohnswort-HealthProfessional/",
    "turmeric":         "https://ods.od.nih.gov/factsheets/Turmeric-HealthProfessional/",
    "valerian":         "https://ods.od.nih.gov/factsheets/Valerian-HealthProfessional/",
    "saw_palmetto":     "https://ods.od.nih.gov/factsheets/Sawpalmetto-HealthProfessional/",
    "soy":              "https://ods.od.nih.gov/factsheets/Soy-HealthProfessional/",
    "aloe_vera":        "https://ods.od.nih.gov/factsheets/Aloevera-HealthProfessional/",
    "cats_claw":        "https://ods.od.nih.gov/factsheets/Catsclaw-HealthProfessional/",
    "chamomile":        "https://ods.od.nih.gov/factsheets/Chamomile-HealthProfessional/",
    "elderberry":       "https://ods.od.nih.gov/factsheets/Elderberry-HealthProfessional/",
    "green_tea":        "https://ods.od.nih.gov/factsheets/Greentea-HealthProfessional/",
    "lavender":         "https://ods.od.nih.gov/factsheets/Lavender-HealthProfessional/",
    "rhodiola":         "https://ods.od.nih.gov/factsheets/Rhodiola-HealthProfessional/",
    "schisandra":       "https://ods.od.nih.gov/factsheets/Schisandra-HealthProfessional/",
}

REQUEST_DELAY = 1.5


def fetch_nih_factsheet(url: str) -> str:
    """Fetch a NIH ODS fact sheet and extract interaction-related text."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Elthio Research Bot/1.0 "
                              "(supplement safety research; "
                              "contact: research@elthio.health)"
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode(errors="replace")

        html = re.sub(r"<script[^>]*>.*?</script>", "", html,
                      flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html,
                      flags=re.DOTALL | re.IGNORECASE)

        relevant_html = html
        toc_match = re.search(
            r'href="#(h\d+)"[^>]*>\s*Interactions with Medications',
            html,
            re.IGNORECASE,
        )
        if toc_match:
            section_id = toc_match.group(1)
            start = html.find(f'id="{section_id}"')
            if start >= 0:
                nxt = re.search(r'id="h\d+"', html[start + 20:])
                end = start + 20 + nxt.start() if nxt else start + 20000
                relevant_html = html[start:end]
        else:
            interactions_match = re.search(
                r"(interactions with medications.*?)(?=<h[23]|$)",
                html,
                re.DOTALL | re.IGNORECASE,
            )
            if interactions_match:
                relevant_html = interactions_match.group(1)

        text = re.sub(r"<[^>]+>", " ", relevant_html)
        text = re.sub(r"\s+", " ", text).strip()

        log.info("Fetched %s: %d chars", url.split("/")[-2], len(text))
        return text[:12000]

    except Exception as e:
        log.warning("Fetch failed for %s: %s", url, e)
        return ""


def extract_interactions_from_text(
    text: str,
    supplement_name: str,
) -> list[dict]:
    """Use Claude to extract drug-supplement interactions from NIH text."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")
    if not text or len(text) < 100:
        return []

    system = """You are a medical data extractor for a supplement safety database.
Extract ALL drug-supplement interactions from NIH fact sheet text.

Return ONLY a valid JSON array — no markdown, no explanation, no backticks.
Each item must follow this exact schema:
{
  "id": "nih-{supplement}-{drug}-{number}",
  "drug": "exact generic drug name or drug class",
  "supplement": "supplement name",
  "severity": "critical|high|moderate|informational",
  "title": "Drug ↔ Supplement — brief title",
  "detail": "what happens when combined (2-3 sentences)",
  "instruction": "what the user should do (1-2 sentences)",
  "mechanism": "why this interaction occurs (1 sentence, if stated)",
  "timing_hours": 0,
  "source": "NIH Office of Dietary Supplements",
  "evidence": "strong|moderate|low",
  "tags": ["relevant", "category", "tags"],
  "synergy": false
}

Severity mapping from NIH language:
- "contraindicated" / "should not be used" / "dangerous" → critical
- "caution" / "may increase risk" / "consult doctor" → high
- "may interact" / "monitor" / "be aware" → moderate
- "may affect" / "possible" / "inform doctor" → informational

Evidence mapping:
- "clinical trials" / "studies show" / "evidence suggests" → strong
- "case reports suggest" / "may" / "some evidence" → moderate
- "theoretical" / "preliminary" / "in vitro" → low

Rules:
- Extract EVERY interaction mentioned, even mild ones
- Use generic drug names not brand names
- If a drug CLASS is mentioned (e.g. "blood thinners"),
  list the class as the drug field
- Keep detail under 200 chars
- Keep instruction under 150 chars
- timing_hours: 0 unless a specific separation time is mentioned
- synergy: true only if the interaction is beneficial
- Return [] if no drug interactions are found in the text
- Do NOT invent interactions not stated in the text"""

    prompt = (
        f"Supplement: {supplement_name}\n\n"
        f"NIH fact sheet text (interactions section):\n{text}\n\n"
        f"Extract all drug interactions. Return JSON array only."
    )

    body = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 4000,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        resp = json.loads(r.read())

    raw = resp["content"][0]["text"].strip()
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()

    try:
        rules = json.loads(raw)
        if not isinstance(rules, list):
            return []
        valid = []
        for rule in rules:
            if (rule.get("drug") and rule.get("supplement")
                    and rule.get("severity") and rule.get("title")):
                valid.append(rule)
        log.info("Extracted %d valid rules for %s", len(valid), supplement_name)
        return valid
    except json.JSONDecodeError as e:
        log.warning("JSON parse error for %s: %s", supplement_name, e)
        return []


def _keyword_list(value: str, extras: list[str] | None = None) -> list[str]:
    """Build deduplicated lowercase keyword list."""
    items: list[str] = []
    for part in [value, *(extras or [])]:
        if not part:
            continue
        for token in re.split(r"[,/]| and ", str(part), flags=re.IGNORECASE):
            token = token.strip().lower()
            if token and token not in items:
                items.append(token)
    return items


def to_elthio_rule(rule: dict, supplement_key: str) -> dict:
    """
    Convert Claude extraction output to interactions_db.json schema
    (med_keywords / supp_keywords) used by med_check_engine.
    """
    drug  = (rule.get("drug") or "").strip()
    supp  = (rule.get("supplement") or supplement_key.replace("_", " ")).strip()
    slug  = re.sub(r"[^a-z0-9]+", "-", f"nih-{supp}-{drug}".lower()).strip("-")
    rule_id = rule.get("id") or slug

    supp_extras = [supplement_key.replace("_", " ")]
    if supp.lower() not in supp_extras:
        supp_extras.append(supp.lower())

    out: dict[str, Any] = {
        "id":            rule_id,
        "title":         rule.get("title") or f"{drug} ↔ {supp}",
        "severity":      rule.get("severity", "moderate"),
        "med_keywords":  _keyword_list(drug),
        "supp_keywords": _keyword_list(supp, supp_extras),
        "detail":        (rule.get("detail") or "")[:500],
        "instruction":   (rule.get("instruction") or "")[:400],
        "source":        rule.get("source") or "NIH Office of Dietary Supplements",
        "pair_type":     "drug_supplement",
    }
    if rule.get("mechanism"):
        out["mechanism"] = rule["mechanism"]
    if rule.get("evidence"):
        out["evidence"] = rule["evidence"]
    if rule.get("tags"):
        out["tags"] = rule["tags"]
    if rule.get("timing_hours"):
        out["timing_hours"] = rule["timing_hours"]
    return out


def _rule_keywords(rule: dict) -> tuple[list[str], list[str]]:
    meds = [k.lower() for k in (rule.get("med_keywords") or rule.get("drugs") or [])]
    sups = [k.lower() for k in (rule.get("supp_keywords") or rule.get("supplements") or [])]
    if not meds and rule.get("drug"):
        meds = _keyword_list(rule["drug"])
    if not sups and rule.get("supplement"):
        sups = _keyword_list(rule["supplement"])
    return meds, sups


def is_duplicate(new_rule: dict, existing_rules: list[dict]) -> bool:
    """Match on drug + supplement keyword overlap."""
    new_meds, new_supps = _rule_keywords(new_rule)

    for existing in existing_rules:
        ex_meds, ex_supps = _rule_keywords(existing)

        drug_match = False
        for nm in new_meds:
            for em in ex_meds:
                if nm == em or nm in em or em in nm:
                    drug_match = True
                    break
            if drug_match:
                break

        supp_match = False
        for ns in new_supps:
            for es in ex_supps:
                if ns == es or ns in es or es in ns:
                    supp_match = True
                    break
            if supp_match:
                break

        if drug_match and supp_match:
            return True
    return False


def expand_rules(
    supplement_filter: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Fetch NIH sheets, extract rules, dedupe, merge into interactions_db.json."""
    existing_rules: list[dict] = []
    if INTERACTIONS_DB.exists():
        with open(INTERACTIONS_DB, encoding="utf-8") as f:
            existing_rules = json.load(f)
    log.info("Existing rules: %d", len(existing_rules))

    supplements_to_process = NIH_ODS_SUPPLEMENTS
    if supplement_filter:
        supplements_to_process = {
            k: v for k, v in NIH_ODS_SUPPLEMENTS.items()
            if supplement_filter.lower().replace(" ", "_") in k.lower()
            or supplement_filter.lower() in k.lower()
        }
        if not supplements_to_process:
            log.warning("No supplement found matching '%s'", supplement_filter)
            return {"error": f"No supplement matching '{supplement_filter}'"}

    log.info("Processing %d supplements...", len(supplements_to_process))

    all_new_rules: list[dict] = []
    total_fetched = 0
    total_extracted = 0
    total_dupes = 0
    failed: list[str] = []

    for supp_key, url in supplements_to_process.items():
        supp_name = supp_key.replace("_", " ")
        log.info("Processing: %s", supp_name)

        text = fetch_nih_factsheet(url)
        if not text:
            log.warning("No content for %s — skipping", supp_name)
            failed.append(supp_name)
            time.sleep(REQUEST_DELAY)
            continue
        total_fetched += 1

        try:
            raw_rules = extract_interactions_from_text(text, supp_name)
        except Exception as e:
            log.error("Extraction failed for %s: %s", supp_name, e)
            failed.append(supp_name)
            time.sleep(REQUEST_DELAY * 2)
            continue

        new_rules = [to_elthio_rule(r, supp_key) for r in raw_rules]
        total_extracted += len(new_rules)

        unique_rules = []
        for rule in new_rules:
            if is_duplicate(rule, existing_rules + all_new_rules):
                total_dupes += 1
            else:
                unique_rules.append(rule)

        all_new_rules.extend(unique_rules)
        log.info(
            "  %s: %d extracted, %d unique, %d dupes",
            supp_name, len(new_rules), len(unique_rules),
            len(new_rules) - len(unique_rules),
        )

        if not dry_run:
            with open(EXPANDED_DB, "w", encoding="utf-8") as f:
                json.dump(all_new_rules, f, indent=2, ensure_ascii=False)

        time.sleep(REQUEST_DELAY)

    log.info(
        "Extraction complete: %d fetched, %d extracted, "
        "%d unique new, %d dupes, %d failed",
        total_fetched, total_extracted,
        len(all_new_rules), total_dupes, len(failed),
    )

    if dry_run:
        log.info("DRY RUN — no files modified")
        return {
            "dry_run":    True,
            "fetched":    total_fetched,
            "extracted":  total_extracted,
            "new_unique": len(all_new_rules),
            "duplicates": total_dupes,
            "failed":     failed,
            "sample":     all_new_rules[:3],
        }

    if not all_new_rules:
        log.warning("No new rules extracted")
        return {
            "merged": False,
            "reason": "No new rules found",
            "failed": failed,
        }

    if INTERACTIONS_DB.exists():
        shutil.copy2(INTERACTIONS_DB, BACKUP_DB)
        log.info("Backup saved to %s", BACKUP_DB)

    merged_rules = existing_rules + all_new_rules
    with open(INTERACTIONS_DB, "w", encoding="utf-8") as f:
        json.dump(merged_rules, f, indent=2, ensure_ascii=False)

    log.info(
        "Merged: %d existing + %d new = %d total rules",
        len(existing_rules), len(all_new_rules), len(merged_rules),
    )

    return {
        "merged":             True,
        "existing_rules":     len(existing_rules),
        "new_rules":          len(all_new_rules),
        "total_rules":        len(merged_rules),
        "duplicates_skipped": total_dupes,
        "failed":             failed,
        "backup":             str(BACKUP_DB),
        "next_step":          "python vector_search.py --index --force",
    }


def get_status() -> dict:
    """Show current state of rule databases."""
    status: dict[str, Any] = {}

    if INTERACTIONS_DB.exists():
        with open(INTERACTIONS_DB, encoding="utf-8") as f:
            rules = json.load(f)
        status["interactions_db"] = {
            "path":  str(INTERACTIONS_DB),
            "rules": len(rules),
        }
    else:
        status["interactions_db"] = {"error": "File not found"}

    if EXPANDED_DB.exists():
        with open(EXPANDED_DB, encoding="utf-8") as f:
            expanded = json.load(f)
        status["expanded_rules"] = {
            "path":  str(EXPANDED_DB),
            "rules": len(expanded),
            "note":  "Partial progress — run again to merge",
        }

    status["nih_supplements_configured"] = len(NIH_ODS_SUPPLEMENTS)
    status["target_rules"] = "400-600 after full extraction"
    return status


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Elthio NIH ODS Rule Expander")
    parser.add_argument(
        "--supplement", help="Process one supplement only (e.g. 'vitamin d')"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Extract but don't save — preview only",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current rule database status",
    )
    parser.add_argument(
        "--merge-only", action="store_true",
        help="Merge existing expanded_rules.json without re-fetching",
    )
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_status(), indent=2))

    elif args.merge_only:
        if not EXPANDED_DB.exists():
            print("No expanded_rules.json found. Run without --merge-only first.")
        else:
            with open(EXPANDED_DB, encoding="utf-8") as f:
                new_rules = json.load(f)
            with open(INTERACTIONS_DB, encoding="utf-8") as f:
                existing = json.load(f)
            merged = existing + new_rules
            shutil.copy2(INTERACTIONS_DB, BACKUP_DB)
            with open(INTERACTIONS_DB, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, ensure_ascii=False)
            print(f"Merged: {len(existing)} + {len(new_rules)} = {len(merged)} rules")
            print("Next: python vector_search.py --index --force")

    else:
        result = expand_rules(
            supplement_filter=args.supplement,
            dry_run=args.dry_run,
        )
        print("\n" + "=" * 60)
        if result.get("dry_run"):
            print("DRY RUN RESULTS:")
            print(f"  Would extract: {result['new_unique']} new rules")
            print(f"  Duplicates skipped: {result['duplicates']}")
            if result.get("sample"):
                print("\n  Sample extracted rules:")
                for r in result["sample"][:2]:
                    print(f"    {r.get('title', '?')} [{r.get('severity', '?')}]")
        elif result.get("merged"):
            print("EXPANSION COMPLETE:")
            print(f"  Previous rules: {result['existing_rules']}")
            print(f"  New rules added: {result['new_rules']}")
            print(f"  Total rules: {result['total_rules']}")
            print(f"  Duplicates skipped: {result['duplicates_skipped']}")
            if result.get("failed"):
                print(f"  Failed: {result['failed']}")
            print(f"\n  Backup saved to: {result['backup']}")
            print(f"\n  NEXT STEP: {result['next_step']}")
        else:
            print(f"Result: {result}")
        print("=" * 60 + "\n")
