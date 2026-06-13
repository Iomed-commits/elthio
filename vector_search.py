"""
vector_search.py — Optimized hybrid RAG for Elthio

Improvements over v1:
1. Multi-entity query decomposition — embeds each drug/supplement
   separately for better recall
2. Severity-weighted re-ranking — critical interactions surface first
3. Structured context assembly — Claude gets organized context not a flat list
4. Parallel embedding calls — faster for multi-entity queries
5. Confidence scoring — each result gets a combined score
6. Graceful degradation — every failure falls back cleanly

Setup:   python vector_search.py --index --force
Search:  python vector_search.py --search "blood thinner fish oil"
Status:  python vector_search.py --status
Test:    python vector_search.py --test
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")
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
SIMILARITY_THRESHOLD = 0.52
TOP_K_PER_ENTITY     = 8
MAX_TOTAL_RESULTS    = 20

DRUG_SUPP_DB = Path(__file__).parent / "interactions_db.json"
SUPP_SUPP_DB = Path(__file__).parent / "supplement_interactions_db.json"

# Severity weights for re-ranking
SEVERITY_WEIGHTS = {
    "critical":      1.0,
    "high":          0.85,
    "moderate":      0.65,
    "informational": 0.40,
}

# Drug synonyms for entity expansion
DRUG_SYNONYMS = {
    "warfarin":      ["warfarin", "coumadin", "blood thinner",
                      "anticoagulant"],
    "levothyroxine": ["levothyroxine", "synthroid", "thyroid medication",
                      "thyroid pill"],
    "metformin":     ["metformin", "glucophage", "diabetes medication",
                      "diabetes pill"],
    "atorvastatin":  ["atorvastatin", "lipitor", "statin",
                      "cholesterol medication"],
    "sertraline":    ["sertraline", "zoloft", "ssri", "antidepressant"],
    "lisinopril":    ["lisinopril", "blood pressure medication",
                      "ace inhibitor"],
    "metoprolol":    ["metoprolol", "lopressor", "beta blocker",
                      "heart medication", "heart pill"],
    "omeprazole":    ["omeprazole", "prilosec", "proton pump inhibitor",
                      "acid reflux", "ppi"],
    "digoxin":       ["digoxin", "lanoxin", "heart medication"],
    "cyclosporine":  ["cyclosporine", "transplant medication",
                      "immunosuppressant"],
    "apixaban":      ["apixaban", "eliquis", "blood thinner",
                      "anticoagulant"],
    "clopidogrel":   ["clopidogrel", "plavix", "blood thinner",
                      "antiplatelet"],
    "amlodipine":    ["amlodipine", "norvasc", "calcium channel blocker",
                      "blood pressure"],
    "amiodarone":    ["amiodarone", "heart rhythm", "arrhythmia"],
    "furosemide":    ["furosemide", "lasix", "water pill", "diuretic",
                      "loop diuretic"],
}


# ── Supabase ──────────────────────────────────────────────────────────────────
def _sh() -> dict:
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
        headers={**_sh(), "Prefer": ""},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
        return json.loads(raw) if raw else []


def supa_get(path: str, params: dict) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_sh())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()) or []


# ── OpenAI embeddings ─────────────────────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")
    body = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text[:8000],
    }).encode()
    req = urllib.request.Request(
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


def get_embeddings_batch(
    texts: list[str],
    batch_size: int = 20,
) -> list[list[float]]:
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        body  = json.dumps({
            "model": EMBEDDING_MODEL,
            "input": batch,
        }).encode()
        req = urllib.request.Request(
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
        log.info(
            "Embedded batch %d-%d of %d",
            i + 1, min(i + batch_size, len(texts)), len(texts)
        )
        time.sleep(0.3)
    return all_embeddings


# ── Rule text builder ─────────────────────────────────────────────────────────
def rule_to_text(rule: dict) -> str:
    parts = []
    for field in ("drug", "supplement", "supplement_a", "supplement_b"):
        if rule.get(field):
            parts.append(
                f"{field.replace('_', ' ').title()}: {rule[field]}"
            )
    drug = rule.get("drug", "").lower()
    if drug in DRUG_SYNONYMS:
        parts.append(
            f"Also known as: {' '.join(DRUG_SYNONYMS[drug])}"
        )
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


# ── Load and index rules ──────────────────────────────────────────────────────
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


def index_rules(force: bool = False) -> int:
    if not force:
        try:
            existing = supa_get(
                "interaction_embeddings",
                {"select": "id", "limit": "1"}
            )
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
    log.info("Got %d embeddings — upserting...", len(embeddings))

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
                    **_sh(),
                    "Prefer": "resolution=merge-duplicates",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=30)
            total_upserted += len(rows)
            log.info("Upserted batch %d-%d", i, i + len(rows))
        except Exception as e:
            log.error("Upsert failed batch %d: %s", i, e)

    log.info("Indexed %d rules into Supabase pgvector", total_upserted)
    return total_upserted


# ── Multi-entity query decomposition ─────────────────────────────────────────
def decompose_query(
    medications: list[str],
    supplements: list[str],
) -> list[str]:
    """
    Break a stack query into multiple focused sub-queries.
    Each drug-supplement pair gets its own query string.
    Generates richer semantic coverage than a single combined query.
    """
    queries = []

    # Full stack query
    if medications and supplements:
        queries.append(
            f"Medications: {', '.join(medications[:3])} — "
            f"Supplements: {', '.join(supplements[:3])}"
        )

    # Per-medication queries with synonym expansion
    for med in medications[:4]:
        med_lower = med.lower()
        synonyms  = DRUG_SYNONYMS.get(med_lower, [med])
        med_str   = " / ".join(synonyms[:3])
        if supplements:
            queries.append(
                f"{med_str} drug interactions with "
                f"{', '.join(supplements[:3])}"
            )
        else:
            queries.append(f"{med_str} supplement interactions")

    # Per-supplement queries
    for supp in supplements[:4]:
        if medications:
            queries.append(
                f"{supp} supplement interactions with "
                f"{', '.join(medications[:3])}"
            )

    # Drug class queries
    drug_classes = []
    for med in medications:
        med_lower = med.lower()
        if any(x in med_lower for x in
               ["warfarin", "apixaban", "clopidogrel", "rivaroxaban"]):
            drug_classes.append("blood thinner anticoagulant")
        if any(x in med_lower for x in
               ["atorvastatin", "simvastatin", "rosuvastatin"]):
            drug_classes.append("statin cholesterol medication")
        if any(x in med_lower for x in
               ["sertraline", "fluoxetine", "escitalopram"]):
            drug_classes.append("ssri antidepressant serotonin")
        if any(x in med_lower for x in
               ["levothyroxine", "thyroid"]):
            drug_classes.append("thyroid medication levothyroxine")

    for drug_class in set(drug_classes):
        if supplements:
            queries.append(
                f"{drug_class} interaction with "
                f"{', '.join(supplements[:2])}"
            )

    return queries[:8]  # Cap at 8 sub-queries


# ── Parallel semantic search ──────────────────────────────────────────────────
def semantic_search_single(
    query: str,
    top_k: int = TOP_K_PER_ENTITY,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Search for a single query string."""
    try:
        embedding = get_embedding(query)
        results   = supa_rpc("match_interactions", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count":     top_k,
            "filter_type":     None,
        })
        matches = []
        for row in (results or []):
            rule = dict(row.get("rule_data", {}))
            rule["_similarity"] = round(row.get("similarity", 0), 4)
            rule["_retrieval"]  = "semantic"
            rule["_rule_type"]  = row.get("rule_type", "")
            matches.append(rule)
        return matches
    except Exception as e:
        log.warning("Semantic search failed for query '%s': %s",
                    query[:50], e)
        return []


def semantic_search_parallel(
    queries: list[str],
    top_k: int = TOP_K_PER_ENTITY,
) -> list[dict]:
    """
    Run multiple semantic searches in parallel.
    Merges and deduplicates results.
    """
    all_results: dict[str, dict] = {}  # keyed by rule id for dedup

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(semantic_search_single, q, top_k): q
            for q in queries
        }
        for future in as_completed(futures):
            try:
                results = future.result(timeout=15)
                for rule in results:
                    rule_id = rule.get("id", rule.get("title", ""))
                    if rule_id not in all_results:
                        all_results[rule_id] = rule
                    else:
                        # Keep highest similarity score
                        existing_sim = all_results[rule_id].get(
                            "_similarity", 0
                        )
                        if rule.get("_similarity", 0) > existing_sim:
                            all_results[rule_id] = rule
            except Exception as e:
                log.warning("Parallel search future failed: %s", e)

    return list(all_results.values())


# ── Severity-weighted re-ranking ──────────────────────────────────────────────
def rerank_results(results: list[dict]) -> list[dict]:
    """
    Re-rank search results by combined score:
    combined_score = similarity × severity_weight × source_quality_weight

    Critical interactions surface above moderate ones even if
    the moderate one had higher cosine similarity.
    """
    def combined_score(rule: dict) -> float:
        similarity = rule.get("_similarity", 0.5)
        severity   = (rule.get("severity") or "informational").lower()
        sev_weight = SEVERITY_WEIGHTS.get(severity, 0.40)

        # Source quality bonus
        source     = (rule.get("source") or "").lower()
        src_weight = 1.0
        if "nih" in source or "fda" in source:
            src_weight = 1.1
        elif "journal" in source or "clinical" in source:
            src_weight = 1.05

        # Evidence quality bonus
        evidence   = (rule.get("evidence") or "").lower()
        ev_weight  = 1.0
        if evidence == "strong":
            ev_weight = 1.1
        elif evidence == "moderate":
            ev_weight = 1.0
        elif evidence in ("low", "preliminary"):
            ev_weight = 0.9

        return similarity * sev_weight * src_weight * ev_weight

    ranked = sorted(results, key=combined_score, reverse=True)

    # Add combined score for transparency
    for rule in ranked:
        rule["_combined_score"] = round(combined_score(rule), 4)

    return ranked


# ── Structured context assembly ───────────────────────────────────────────────
def assemble_context(
    interactions:     list[dict],
    synergies:        list[dict],
    timing_conflicts: list[dict],
    near_misses:      list[dict],
) -> str:
    """
    Build structured context string for Claude.
    Groups by category instead of flat list.
    Claude gets cleaner, more organized context.
    """
    parts = []

    if interactions:
        parts.append("DRUG-SUPPLEMENT INTERACTIONS (ranked by severity):")
        for ix in interactions[:8]:
            sev  = ix.get("severity", "").upper()
            title= ix.get("title", "")
            inst = ix.get("instruction", "")[:100] if ix.get("instruction") else ""
            src  = ix.get("source", "")
            parts.append(
                f"  [{sev}] {title}"
                + (f" — {inst}" if inst else "")
                + (f" (Source: {src})" if src else "")
            )

    if synergies:
        parts.append("\nBENEFICIAL COMBINATIONS:")
        for s in synergies[:4]:
            parts.append(
                f"  ✓ {s.get('title', '')} — "
                f"{s.get('detail', '')[:80] if s.get('detail') else ''}"
            )

    if timing_conflicts:
        parts.append("\nTIMING CONFLICTS (separate these):")
        for t in timing_conflicts[:3]:
            hrs = t.get("timing_hours", 2)
            parts.append(
                f"  ⏱ {t.get('supplement_a', '')} + "
                f"{t.get('supplement_b', '')} — "
                f"separate by {hrs}+ hours"
            )

    if near_misses:
        parts.append("\nNEAR-MATCHES (possible interactions):")
        for nm in near_misses[:3]:
            if isinstance(nm, dict):
                parts.append(f"  ~ {nm.get('title', '')}")
            else:
                parts.append(f"  ~ {nm}")

    return "\n".join(parts)


# ── Main hybrid search ────────────────────────────────────────────────────────
def hybrid_search(
    medications: list[str],
    supplements: list[str],
    top_k: int = TOP_K_PER_ENTITY,
) -> dict:
    """
    Optimized hybrid search:
    1. Decompose query into multiple entity-focused sub-queries
    2. Run parallel semantic search across all sub-queries
    3. Run keyword search (med_check_engine)
    4. Merge, deduplicate, re-rank by severity × similarity
    5. Assemble structured context for Claude
    """
    # Step 1 — Query decomposition
    queries = decompose_query(medications, supplements)
    log.info("Decomposed into %d sub-queries", len(queries))

    # Step 2 — Parallel semantic search
    semantic_results = []
    try:
        semantic_results = semantic_search_parallel(queries, top_k)
        log.info("Semantic: %d unique results across %d queries",
                 len(semantic_results), len(queries))
    except Exception as e:
        log.warning("Semantic search unavailable: %s", e)

    # Step 3 — Keyword search
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
        return {
            **keyword_data,
            "retrieval_method": "keyword",
            "rules_checked":    334,
            "semantic_matches": 0,
            "context":          assemble_context(
                keyword_data["interactions"],
                keyword_data["synergies"],
                keyword_data["timing_conflicts"],
                keyword_data["near_misses"],
            ),
        }

    # Step 4 — Merge and deduplicate
    def _rule_id(item: dict | str) -> str:
        if isinstance(item, dict):
            return item.get("id", item.get("title", "")) or ""
        return str(item)

    seen_ids = {
        rid
        for ix in keyword_data["interactions"] + keyword_data["near_misses"]
        if (rid := _rule_id(ix))
    }

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
        min_sim = 0.75 if sev in ("critical", "high") else 0.52

        if similarity < min_sim:
            sem_near_misses.append({**rule, "_source": "semantic_low"})
        elif rule.get("synergy"):
            sem_synergies.append({**rule, "_source": "semantic"})
        elif rule.get("type") == "timing_conflict":
            sem_timing.append({**rule, "_source": "semantic"})
        elif sev in ("critical", "high", "moderate"):
            sem_interactions.append({**rule, "_source": "semantic"})
        else:
            sem_near_misses.append({**rule, "_source": "semantic"})

    # Step 5 — Re-rank by severity × similarity
    all_interactions = rerank_results(
        keyword_data["interactions"] + sem_interactions
    )[:MAX_TOTAL_RESULTS]

    all_synergies    = (keyword_data["synergies"]   + sem_synergies)[:8]
    all_timing       = (keyword_data["timing_conflicts"] + sem_timing)[:6]
    all_near_misses  = (keyword_data["near_misses"] + sem_near_misses)[:8]

    # Step 6 — Structured context
    context = assemble_context(
        all_interactions, all_synergies,
        all_timing, all_near_misses
    )

    return {
        "interactions":     all_interactions,
        "near_misses":      all_near_misses,
        "synergies":        all_synergies,
        "timing_conflicts": all_timing,
        "retrieval_method": "hybrid_v2",
        "rules_checked":    334 + len(semantic_results),
        "semantic_matches": len(sem_interactions) + len(sem_synergies),
        "sub_queries":      len(queries),
        "context":          context,
    }


# ── Status ────────────────────────────────────────────────────────────────────
def get_status() -> dict:
    try:
        url = (f"{SUPABASE_URL}/rest/v1/interaction_embeddings"
               f"?select=count")
        req = urllib.request.Request(
            url,
            headers={
                **_sh(),
                "Prefer":     "count=exact",
                "Range-Unit": "items",
                "Range":      "0-0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            cr    = r.headers.get("Content-Range", "0/0")
            total = int(cr.split("/")[-1])

        last_indexed = None
        try:
            recent = supa_get("interaction_embeddings", {
                "select": "created_at",
                "order":  "created_at.desc",
                "limit":  "1",
            })
            if recent:
                last_indexed = recent[0].get("created_at")
        except Exception:
            pass

        return {
            "pgvector":     "ready",
            "rules_count":  total,
            "status":       "ready" if total > 0 else "empty",
            "version":      "v2_optimized",
            "last_indexed": last_indexed,
        }
    except Exception as e:
        return {
            "pgvector": "unavailable",
            "error":    str(e),
            "status":   "fallback_to_keyword",
        }


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Elthio pgvector Search v2"
    )
    parser.add_argument("--index",  action="store_true")
    parser.add_argument("--force",  action="store_true")
    parser.add_argument("--search", help="Search query")
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
        # Parse as medications + supplements for decomposition
        print(f"\nSearching: '{args.search}'\n")
        queries = decompose_query(
            medications  = [args.search],
            supplements  = [],
        )
        print(f"Decomposed into {len(queries)} sub-queries:")
        for q in queries:
            print(f"  · {q}")
        print()
        results = semantic_search_parallel(queries, top_k=5)
        results = rerank_results(results)
        print(f"Top {min(5, len(results))} re-ranked results:\n")
        for r in results[:5]:
            print(
                f"  [{r.get('_combined_score', 0):.3f}]  "
                f"{r.get('title', r.get('id', '?'))}"
            )
            print(
                f"           sim={r.get('_similarity',0):.3f}  "
                f"sev={r.get('severity','?')}  "
                f"type={r.get('_rule_type','?')}"
            )
        print()

    elif args.test:
        print("\n=== PGVECTOR v2 SELF TEST ===\n")

        print("[1] Status")
        s = get_status()
        print(f"  pgvector:  {s['pgvector']}")
        print(f"  rules:     {s.get('rules_count', 0)}")
        print(f"  version:   {s.get('version', 'unknown')}")

        if s.get("rules_count", 0) == 0:
            print("\n  Run: python vector_search.py --index")
        else:
            print("\n[2] Query decomposition")
            qs = decompose_query(
                medications=["warfarin"],
                supplements=["fish oil", "vitamin k2"]
            )
            print(f"  Decomposed into {len(qs)} sub-queries:")
            for q in qs[:3]:
                print(f"    · {q[:70]}")

            print("\n[3] Parallel semantic search")
            results = semantic_search_parallel(qs[:3], top_k=3)
            print(f"  {len(results)} unique results across queries")

            print("\n[4] Re-ranking")
            ranked = rerank_results(results)
            for r in ranked[:3]:
                print(
                    f"  [{r.get('_combined_score',0):.3f}]  "
                    f"{r.get('title','?')[:50]}  "
                    f"({r.get('severity','?')})"
                )

            print("\n[5] Full hybrid search — warfarin stack")
            h = hybrid_search(
                medications=["warfarin"],
                supplements=["fish oil", "vitamin k2", "coq10"],
            )
            print(f"  Interactions:  {len(h['interactions'])}")
            print(f"  Synergies:     {len(h['synergies'])}")
            print(f"  Method:        {h['retrieval_method']}")
            print(f"  Sub-queries:   {h['sub_queries']}")
            print(f"  Semantic hits: {h['semantic_matches']}")
            print(f"\n  Structured context preview:")
            for line in h['context'].split('\n')[:6]:
                print(f"    {line}")

            print("\n[6] Natural language — 'heart pill fish oil'")
            h2 = hybrid_search(
                medications=["heart pill"],
                supplements=["fish oil"],
            )
            print(f"  Interactions:  {len(h2['interactions'])}")
            print(f"  Semantic hits: {h2['semantic_matches']}")

        print("\n=== TEST COMPLETE ===\n")

    else:
        parser.print_help()
