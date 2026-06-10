"""
vector_search.py — Semantic vector search using Supabase pgvector

Stores 174 interaction rules as embeddings in Supabase.
Queries match by meaning not keywords — "heart pill" finds "warfarin" rules.
Zero new infrastructure — uses your existing Supabase database.

Setup:   python vector_search.py --index
Search:  python vector_search.py --search "blood thinner and fish oil"
Status:  python vector_search.py --status
Test:    python vector_search.py --test
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from supabase_client import normalize_supabase_url

OPENAI_API_KEY       = os.environ.get("OPENAI_API_KEY", "")
SUPABASE_URL         = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY         = (
    os.environ.get("SUPABASE_KEY", "")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
)
EMBEDDING_MODEL      = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.55
TOP_K                = 10

DRUG_SUPP_DB = Path(__file__).parent / "interactions_db.json"
SUPP_SUPP_DB = Path(__file__).parent / "supplement_interactions_db.json"

DRUG_SYNONYMS = {
    "warfarin":      "warfarin coumadin blood thinner anticoagulant",
    "levothyroxine": "levothyroxine synthroid thyroid medication thyroid pill",
    "metformin":     "metformin glucophage diabetes medication diabetes pill",
    "atorvastatin":  "atorvastatin lipitor statin cholesterol medication",
    "sertraline":    "sertraline zoloft ssri antidepressant",
    "lisinopril":    "lisinopril blood pressure medication ace inhibitor",
    "metoprolol":    "metoprolol lopressor beta blocker heart medication heart pill",
    "omeprazole":    "omeprazole prilosec proton pump inhibitor acid reflux",
    "digoxin":       "digoxin lanoxin heart medication cardiac",
    "cyclosporine":  "cyclosporine transplant medication immunosuppressant",
    "apixaban":      "apixaban eliquis blood thinner anticoagulant",
    "clopidogrel":   "clopidogrel plavix blood thinner antiplatelet",
    "amlodipine":    "amlodipine norvasc calcium channel blocker blood pressure",
    "amiodarone":    "amiodarone heart rhythm arrhythmia",
}


# ── Supabase helpers ──────────────────────────────────────────────────────────
def _supa_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def supa_rpc(fn: str, params: dict) -> Any:
    url  = f"{SUPABASE_URL}/rest/v1/rpc/{fn}"
    data = json.dumps(params).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={**_supa_headers(), "Prefer": ""},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def supa_get(path: str, params: dict) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_supa_headers())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


# ── OpenAI embeddings ─────────────────────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")
    body = json.dumps({"model": EMBEDDING_MODEL, "input": text[:8000]}).encode()
    req  = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=body,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["data"][0]["embedding"]


def get_embeddings_batch(texts: list[str], batch_size: int = 20) -> list[list[float]]:
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        body  = json.dumps({"model": EMBEDDING_MODEL, "input": batch}).encode()
        req   = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=body,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        batch_embeddings = [
            item["embedding"]
            for item in sorted(data["data"], key=lambda x: x["index"])
        ]
        all_embeddings.extend(batch_embeddings)
        log.info("Embedded batch %d-%d of %d", i + 1,
                 min(i + batch_size, len(texts)), len(texts))
        time.sleep(0.3)
    return all_embeddings


# ── Rule text builder ─────────────────────────────────────────────────────────
def rule_to_text(rule: dict) -> str:
    parts = []
    for field in ("drug", "supplement", "supplement_a", "supplement_b"):
        if rule.get(field):
            parts.append(f"{field.replace('_', ' ').title()}: {rule[field]}")
    drug = rule.get("drug", "").lower()
    if drug in DRUG_SYNONYMS:
        parts.append(f"Also known as: {DRUG_SYNONYMS[drug]}")
    if rule.get("severity"):
        parts.append(f"Severity: {rule['severity']}")
    if rule.get("title"):
        parts.append(f"Interaction: {rule['title']}")
    for field in ("detail", "mechanism", "instruction"):
        if rule.get(field):
            parts.append(f"{field.title()}: {rule[field]}")
    tags = rule.get("tags", [])
    if isinstance(tags, list) and tags:
        parts.append(f"Categories: {', '.join(tags)}")
    return "\n".join(parts)


# ── Load rules ────────────────────────────────────────────────────────────────
def load_all_rules() -> list[tuple[dict, str]]:
    rules = []
    for path, rule_type in [
        (DRUG_SUPP_DB, "drug_supplement"),
        (SUPP_SUPP_DB, "supplement_supplement"),
    ]:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                batch = json.load(f)
            rules.extend((r, rule_type) for r in batch)
            log.info("Loaded %d rules from %s", len(batch), path.name)
        else:
            log.warning("Not found: %s", path)
    return rules


# ── Index rules ───────────────────────────────────────────────────────────────
def index_rules(force: bool = False) -> int:
    if not force:
        try:
            existing = supa_get("interaction_embeddings", {"select": "id", "limit": "1"})
            if existing:
                log.info("Already indexed. Use --force to re-index.")
                return -1
        except Exception:
            pass

    rules_and_types = load_all_rules()
    if not rules_and_types:
        log.error("No rules found")
        return 0

    rules      = [r for r, _ in rules_and_types]
    rule_types = [t for _, t in rules_and_types]
    texts      = [rule_to_text(r) for r in rules]

    log.info("Building embeddings for %d rules...", len(texts))
    embeddings = get_embeddings_batch(texts)
    log.info("Got %d embeddings — upserting to Supabase...", len(embeddings))

    batch_size     = 20
    total_upserted = 0

    for i in range(0, len(rules), batch_size):
        batch_rules  = rules[i:i + batch_size]
        batch_types  = rule_types[i:i + batch_size]
        batch_embeds = embeddings[i:i + batch_size]

        rows = []
        for j, (rule, rtype, emb) in enumerate(
            zip(batch_rules, batch_types, batch_embeds)
        ):
            rows.append({
                "id":        rule.get("id", f"rule-{i+j}"),
                "rule_data": rule,
                "rule_type": rtype,
                "severity":  rule.get("severity", "informational"),
                "is_synergy":bool(rule.get("synergy", False)),
                "embedding": emb,
            })

        try:
            url  = f"{SUPABASE_URL}/rest/v1/interaction_embeddings"
            data = json.dumps(rows).encode()
            req  = urllib.request.Request(
                url, data=data,
                headers={
                    **_supa_headers(),
                    "Prefer": "resolution=merge-duplicates",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=30)
            total_upserted += len(rows)
            log.info("Upserted batch %d-%d", i, i + len(rows))
        except Exception as e:
            log.error("Upsert failed for batch %d: %s", i, e)

    log.info("Indexed %d rules into Supabase pgvector", total_upserted)
    return total_upserted


# ── Semantic search ───────────────────────────────────────────────────────────
def semantic_search(
    query: str,
    top_k: int = TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
    rule_type: str | None = None,
) -> list[dict]:
    try:
        embedding = get_embedding(query)
        results   = supa_rpc("match_interactions", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count":     top_k,
            "filter_type":     rule_type,
        })
        matches = []
        for row in (results or []):
            rule = dict(row.get("rule_data", {}))
            rule["_similarity"] = round(row.get("similarity", 0), 4)
            rule["_retrieval"]  = "semantic"
            rule["_rule_type"]  = row.get("rule_type", "")
            matches.append(rule)
        log.info("Semantic search: %d matches for '%s'", len(matches), query[:60])
        return matches
    except Exception as e:
        log.warning("Semantic search failed: %s", e)
        return []


# ── Query builder ─────────────────────────────────────────────────────────────
def build_search_query(medications: list[str], supplements: list[str]) -> str:
    parts = []
    if medications:
        parts.append(f"Medications: {', '.join(medications)}")
    if supplements:
        parts.append(f"Supplements: {', '.join(supplements)}")
    if medications and supplements:
        parts.append(
            f"Interaction between {', '.join(medications[:3])} "
            f"and {', '.join(supplements[:3])}"
        )
    return "\n".join(parts)


# ── Hybrid search ─────────────────────────────────────────────────────────────
def hybrid_search(
    medications: list[str],
    supplements: list[str],
    top_k: int = TOP_K,
) -> dict:
    query            = build_search_query(medications, supplements)
    semantic_results = []
    try:
        semantic_results = semantic_search(query, top_k=top_k * 2)
    except Exception as e:
        log.warning("Semantic search unavailable: %s", e)

    keyword_data = {
        "interactions": [], "near_misses": [],
        "synergies": [], "timing_conflicts": [],
    }
    try:
        from med_check_engine import run_med_check
        kw = run_med_check(medications, supplements, [])
        keyword_data["interactions"] = kw.get("interactions", [])
        keyword_data["near_misses"]  = kw.get("near_misses",  [])
    except Exception as e:
        log.warning("Keyword search error: %s", e)

    try:
        from med_check_engine import check_supplement_interactions
        supp = check_supplement_interactions(supplements)
        keyword_data["interactions"]    += supp.get("interactions",     [])
        keyword_data["near_misses"]     += supp.get("near_misses",      [])
        keyword_data["synergies"]        = supp.get("synergies",        [])
        keyword_data["timing_conflicts"] = supp.get("timing_conflicts", [])
    except Exception as e:
        log.warning("Supplement check error: %s", e)

    if not semantic_results:
        return {**keyword_data, "retrieval_method": "keyword",
                "rules_checked": 174, "semantic_matches": 0}

    seen_ids         = {
        ix.get("id", ix.get("title", ""))
        for ix in keyword_data["interactions"] + keyword_data["near_misses"]
    }
    severity_order   = {"critical": 0, "high": 1, "moderate": 2, "informational": 3}
    sem_interactions = []
    sem_near_misses  = []
    sem_synergies    = []
    sem_timing       = []

    for rule in semantic_results:
        rule_id    = rule.get("id", rule.get("title", ""))
        similarity = rule.get("_similarity", 0)
        if rule_id in seen_ids:
            continue
        seen_ids.add(rule_id)

        sev     = (rule.get("severity") or "informational").lower()
        min_sim = 0.80 if sev in ("critical", "high") else SIMILARITY_THRESHOLD

        if similarity < min_sim:
            sem_near_misses.append({**rule, "_source": "semantic_low_conf"})
        elif rule.get("synergy"):
            sem_synergies.append({**rule, "_source": "semantic"})
        elif rule.get("type") == "timing_conflict":
            sem_timing.append({**rule, "_source": "semantic"})
        elif sev in ("critical", "high", "moderate"):
            sem_interactions.append({**rule, "_source": "semantic"})
        else:
            sem_near_misses.append({**rule, "_source": "semantic"})

    all_interactions = keyword_data["interactions"] + sem_interactions
    all_interactions.sort(
        key=lambda x: severity_order.get(
            (x.get("severity") or "informational").lower(), 3
        )
    )

    return {
        "interactions":     all_interactions[:15],
        "near_misses":      (keyword_data["near_misses"] + sem_near_misses)[:10],
        "synergies":        (keyword_data["synergies"]   + sem_synergies)[:10],
        "timing_conflicts": (keyword_data["timing_conflicts"] + sem_timing)[:10],
        "retrieval_method": "hybrid",
        "rules_checked":    174 + len(semantic_results),
        "semantic_matches": len(sem_interactions) + len(sem_synergies),
    }


# ── Status ────────────────────────────────────────────────────────────────────
def get_status() -> dict:
    try:
        url = f"{SUPABASE_URL}/rest/v1/interaction_embeddings?select=count"
        req = urllib.request.Request(
            url,
            headers={
                **_supa_headers(),
                "Prefer":     "count=exact",
                "Range-Unit": "items",
                "Range":      "0-0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            content_range = r.headers.get("Content-Range", "0/0")
            total = int(content_range.split("/")[-1])
        return {
            "pgvector":    "ready",
            "table":       "interaction_embeddings",
            "rules_count": total,
            "status":      "ready" if total > 0 else "empty",
        }
    except Exception as e:
        return {"pgvector": "unavailable", "error": str(e),
                "status": "fallback_to_keyword"}


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / ".env")
        OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
        SUPABASE_URL   = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
        SUPABASE_KEY   = (
            os.environ.get("SUPABASE_KEY", "")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        )
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Elthio pgvector Search")
    parser.add_argument("--index",  action="store_true")
    parser.add_argument("--force",  action="store_true")
    parser.add_argument("--search", help="Semantic search query")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--test",   action="store_true")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_status(), indent=2))

    elif args.index:
        n = index_rules(force=args.force)
        if n == -1:
            print("Already indexed. Use --force to re-index.")
        else:
            print(f"Indexed {n} rules into Supabase pgvector")

    elif args.search:
        results = semantic_search(args.search, top_k=5)
        print(f"\nTop {len(results)} results for '{args.search}':\n")
        for r in results:
            print(f"  [{r.get('_similarity', 0):.3f}]  "
                  f"{r.get('title', r.get('id', '?'))}")
            print(f"           severity={r.get('severity', '?')}  "
                  f"type={r.get('_rule_type', '?')}")
        print()

    elif args.test:
        print("\n=== PGVECTOR SELF TEST ===\n")

        print("[1] Status")
        s = get_status()
        print(f"  pgvector: {s['pgvector']}")
        print(f"  rules:    {s.get('rules_count', 0)}")
        print(f"  status:   {s['status']}")

        if s.get("rules_count", 0) == 0:
            print("\n  No rules indexed. Run: python vector_search.py --index")
        else:
            print("\n[2] Heart pill + fish oil")
            r = semantic_search("heart pill and fish oil", top_k=3)
            for x in r:
                print(f"  [{x['_similarity']:.3f}]  {x.get('title', '?')}")

            print("\n[3] Thyroid synonym match")
            r2 = semantic_search("thyroid medication and calcium", top_k=3)
            for x in r2:
                print(f"  [{x['_similarity']:.3f}]  {x.get('title', '?')}")

            print("\n[4] Hybrid search — warfarin stack")
            h = hybrid_search(
                medications=["warfarin"],
                supplements=["fish oil", "vitamin k2", "coq10"],
            )
            print(f"  Interactions:  {len(h['interactions'])}")
            print(f"  Synergies:     {len(h['synergies'])}")
            print(f"  Method:        {h['retrieval_method']}")
            print(f"  Semantic hits: {h['semantic_matches']}")

            print("\n[5] Natural language query")
            r3 = semantic_search("blood thinner supplement bleeding risk", top_k=5)
            print(f"  Found {len(r3)} matches")
            for x in r3[:3]:
                print(f"  [{x['_similarity']:.3f}]  {x.get('title', '?')}")

        print("\n=== TEST COMPLETE ===\n")

    else:
        parser.print_help()
