"""
healthcheck.py — Elthio Pre-Launch Health Check
Run before every deployment to confirm all engines and endpoints work.

Usage:
    python healthcheck.py              # engine tests only (no server needed)
    python healthcheck.py --full       # engine + endpoint tests (server must be running)
    python healthcheck.py --endpoints  # endpoint tests only
"""

from __future__ import annotations
import sys
import time
import json
import argparse
from typing import Callable

BASE_URL = "http://127.0.0.1:8765"
PASS = "✓"
FAIL = "✗"
WARN = "⚠"

results: list[dict] = []


def _safe_stdout():
    # Windows consoles can default to cp1252 and choke on ✓/⚠/✗.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def test(name: str, fn: Callable, critical: bool = True) -> bool:
    start = time.time()
    try:
        msg = fn()
        elapsed = round(time.time() - start, 2)
        results.append({"name": name, "status": "pass", "msg": msg, "elapsed": elapsed, "critical": critical})
        print(f"  {PASS}  {name} ({elapsed}s)")
        if msg:
            print(f"       {msg}")
        return True
    except AssertionError as e:
        elapsed = round(time.time() - start, 2)
        results.append({"name": name, "status": "fail", "msg": str(e), "elapsed": elapsed, "critical": critical})
        print(f"  {FAIL}  {name} ({elapsed}s)")
        print(f"       {e}")
        return False
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        results.append({"name": name, "status": "error", "msg": str(e), "elapsed": elapsed, "critical": critical})
        print(f"  {FAIL}  {name} ({elapsed}s)")
        print(f"       {e}")
        return False


def warn(name: str, fn: Callable) -> bool:
    return test(name, fn, critical=False)


# ── ENGINE TESTS ─────────────────────────────────────────────────────────────

def run_engine_tests():
    print("\n── Engine tests ─────────────────────────────────────────────────")

    test("rules.py loads", lambda: (
        __import__("rules") and
        f"{len(__import__('rules').RULES)} rules loaded"
    ))

    test("separation_coach imports", lambda: (
        __import__("separation_coach") and "OK"
    ))

    test("Separation Coach — Warfarin + Magnesium", lambda: (
        _check_coach(
            meds=["Warfarin"],
            supps=[{"name": "Magnesium Glycinate"}],
            expect_blocks=["evening", "bedtime"],
            expect_min_rules=1,
        )
    ))

    test("Separation Coach — supplement-only stack", lambda: (
        _check_coach(
            meds=[],
            supps=["Vitamin D3", "Vitamin B Complex", "Biotin", "Ginseng"],
            expect_blocks=["morning", "fatty_meal"],
            expect_min_rules=2,
        )
    ))

    test("Separation Coach — synergy suggestions fire", lambda: (
        _check_synergy(
            supps=["Vitamin D3"],
            expect_suggestions=True,
        )
    ))

    test("Med Check — Warfarin + Vitamin K2 is CRITICAL", lambda: (
        _check_med(
            meds=["warfarin"],
            supps=["vitamin k2"],
            expect_severity="critical",
        )
    ))

    test("Med Check — Levothyroxine + Magnesium is CRITICAL", lambda: (
        _check_med(
            meds=["levothyroxine"],
            supps=["magnesium glycinate"],
            expect_severity="critical",
        )
    ))

    test("Med Check — Metformin + Vitamin B12 is HIGH", lambda: (
        _check_med(
            meds=["metformin"],
            supps=["vitamin b12"],
            expect_severity="high",
        )
    ))

    test("Med Check — near-misses fire for no match", lambda: (
        _check_near_miss(
            meds=["metformin"],
            supps=["vitamin k2"],
        )
    ))

    test("Shopping Agent — parse query", lambda: (
        _check_parse_query(
            query="magnesium glycinate under $25",
            expect_supplement="magnesium",
            expect_budget=25,
        )
    ))

    test("Shopping Agent — fallback catalog returns results", lambda: (
        _check_fallback("magnesium glycinate under $25", expect_min=2)
    ))

    test("Shopping Agent — Doctor's Best beats California Gold for magnesium", lambda: (
        _check_ranking()
    ))

    test("Basket Compare — type detection", lambda: (
        _check_type_detection()
    ))

    test("Basket Compare — Life Extension catalog coverage", lambda: (
        _check_le_catalog()
    ))

    test("Basket Compare — shipping math correct", lambda: (
        _check_shipping_math()
    ))


def _check_coach(meds, supps, expect_blocks, expect_min_rules):
    from separation_coach import generate_separation_schedule
    result = generate_separation_schedule(meds, supps)
    j = result.to_json()
    block_ids = [b["id"] for b in j["blocks"]]
    missing = [b for b in expect_blocks if b not in block_ids]
    assert not missing, f"Missing blocks: {missing} — got {block_ids}"
    assert j["rules_matched"] >= expect_min_rules, \
        f"Expected ≥{expect_min_rules} rules, got {j['rules_matched']}"
    um = j["unmatched"]["medications"] + j["unmatched"]["supplements"]
    assert not um, f"Unmatched items: {um}"
    return f"{j['rules_matched']} rules, blocks: {block_ids}"


def _check_synergy(supps, expect_suggestions):
    from separation_coach import generate_separation_schedule
    result = generate_separation_schedule([], supps)
    j = result.to_json()
    has = len(j.get("synergy_suggestions", [])) > 0
    assert has == expect_suggestions, \
        f"Expected synergy={expect_suggestions}, got {len(j.get('synergy_suggestions',[]))} suggestions"
    return f"{len(j.get('synergy_suggestions',[]))} synergy suggestion(s)"


def _check_med(meds, supps, expect_severity):
    from med_check_engine import run_med_check
    result = run_med_check(meds, supps, [])
    interactions = result.get("interactions", [])
    assert interactions, f"No interactions found for {meds} + {supps}"
    severities = [i["severity"] for i in interactions]
    assert expect_severity in severities, \
        f"Expected severity '{expect_severity}', got {severities}"
    return f"{len(interactions)} interaction(s), severities: {severities}"


def _check_near_miss(meds, supps):
    from med_check_engine import run_med_check
    result = run_med_check(meds, supps, [])
    interactions = result.get("interactions", [])
    near_misses = result.get("near_misses", [])
    assert not interactions, f"Expected 0 interactions, got {len(interactions)}"
    assert near_misses, f"Expected near-misses but got none"
    return f"0 interactions, {len(near_misses)} near-miss(es)"


def _check_parse_query(query, expect_supplement, expect_budget):
    from shopping_agent import parse_query
    intent = parse_query(query)
    assert intent["supplement"] == expect_supplement, \
        f"Expected supplement '{expect_supplement}', got '{intent['supplement']}'"
    assert intent["budget"] == expect_budget, \
        f"Expected budget {expect_budget}, got {intent['budget']}"
    return f"supplement={intent['supplement']}, budget={intent['budget']}"


def _check_fallback(query, expect_min):
    from shopping_agent import parse_query, get_fallback_products
    intent = parse_query(query)
    products = get_fallback_products(intent)
    assert len(products) >= expect_min, \
        f"Expected ≥{expect_min} fallback products, got {len(products)}"
    return f"{len(products)} fallback products"


def _check_ranking():
    from shopping_agent import parse_query, rank_products
    products = [
        {"brand": "California Gold Nutrition", "product_name": "Magnesium Bisglycinate 60 caps",
         "price": 9.22, "servings": 60, "form": "magnesium glycinate"},
        {"brand": "Doctor's Best", "product_name": "High Absorption Magnesium Glycinate 240 tabs",
         "price": 20.99, "servings": 240, "form": "magnesium glycinate"},
    ]
    intent = parse_query("best magnesium glycinate under $25")
    result = rank_products(products, intent)
    candidates = result["candidates"]
    assert candidates, "No candidates returned"
    top = candidates[0]
    assert "doctor" in top.get("brand", "").lower(), \
        f"Expected Doctor's Best as top pick, got {top.get('brand')}"
    return f"Top pick: {top['brand']} at ${top.get('cost_per_serving',0):.3f}/serving"


def _check_type_detection():
    from basket_compare import detect_supplement_type
    tests = [
        ("CoQ10",            "coq10"),
        ("D3+K2",            "vitamin d"),
        ("Mg glycinate",     "magnesium"),
        ("Ubiquinol 200mg",  "coq10"),
        ("fish oil 1000mg",  "omega-3"),
        ("methylcobalamin",  "vitamin b12"),
        ("Iron bisglycinate","iron"),
        ("vitamin c 1000",   "vitamin c"),
    ]
    failures = []
    for query, expected in tests:
        result = detect_supplement_type(query)
        if result != expected:
            failures.append(f"'{query}' -> {result} (expected {expected})")
    assert not failures, "Type detection failures:\n  " + "\n  ".join(failures)
    return f"{len(tests)}/{len(tests)} type detection tests passed"


def _check_le_catalog():
    from basket_compare import get_life_extension_products
    required_types = [
        "magnesium", "vitamin d", "coq10", "zinc", "iron",
        "vitamin c", "omega-3", "vitamin b12", "calcium",
        "vitamin k", "probiotics", "biotin", "selenium", "melatonin",
    ]
    missing = []
    for t in required_types:
        products = get_life_extension_products(t)
        if not products:
            missing.append(t)
    assert not missing, f"Life Extension catalog missing: {missing}"
    return f"All {len(required_types)} supplement types covered"


def _check_shipping_math():
    from basket_compare import build_mix_and_match
    mock = {
        "iherb": [
            {"brand": "Thorne", "product_name": "Iron", "price": 14.00,
             "retailer": "iherb", "retailer_name": "iHerb"},
            {"brand": "NOW", "product_name": "CoQ10", "price": 22.99,
             "retailer": "iherb", "retailer_name": "iHerb"},
        ],
        "life_extension": [
            {"brand": "LE", "product_name": "Iron LE", "price": 12.00,
             "retailer": "life_extension", "retailer_name": "Life Extension"},
            {"brand": "LE", "product_name": "CoQ10 LE", "price": 34.50,
             "retailer": "life_extension", "retailer_name": "Life Extension"},
        ],
    }
    mix = build_mix_and_match(mock, ["Iron", "CoQ10"])
    assert mix["total_with_shipping"] >= mix["items_total"], \
        "Shipping math broken: total_with_shipping < items_total"
    assert mix["items_total"] > 0, "Items total is zero"
    return (f"items_total=${mix['items_total']:.2f}, "
            f"with_shipping=${mix['total_with_shipping']:.2f}")


# ── ENDPOINT TESTS ───────────────────────────────────────────────────────────

def run_endpoint_tests():
    print("\n── Endpoint tests (server must be running at 8765) ──────────────")
    try:
        import urllib.request
        urllib.request.urlopen(f"{BASE_URL}/config", timeout=3)
    except Exception:
        results.append({
            "name": "Server reachable",
            "status": "fail",
            "msg": f"Server not running at {BASE_URL}",
            "elapsed": 0.0,
            "critical": True,
        })
        print(f"  {FAIL}  Server not running at {BASE_URL} — start with: python server.py")
        return False

    test("GET / returns elthio.html", lambda: _get("/"))

    test("GET /config returns Supabase credentials", lambda: (
        _check_config()
    ))

    test("POST /api/separation-schedule", lambda: (
        _post_check(
            "/api/separation-schedule",
            {"medications": ["Warfarin"], "supplements": ["Magnesium Glycinate", "Vitamin D3"]},
            checks=[
                lambda d: "blocks" in d,
                lambda d: d.get("rules_matched", 0) >= 1,
                lambda d: len(d.get("blocks", [])) >= 2,
            ],
            description="blocks present, ≥1 rule, ≥2 blocks",
        )
    ))

    test("POST /med-check — Warfarin + Vitamin K2 = CRITICAL", lambda: (
        _post_check(
            "/med-check",
            {"medications": ["warfarin"], "supplements": ["vitamin k2"]},
            checks=[
                lambda d: len(d.get("interactions", [])) >= 1,
                lambda d: d["interactions"][0]["severity"] == "critical",
            ],
            description="1+ interaction, severity=critical",
        )
    ))

    test("POST /api/shopping-agent — magnesium glycinate", lambda: (
        _post_check(
            "/api/shopping-agent",
            {"query": "magnesium glycinate under $25"},
            checks=[
                lambda d: "candidates" in d,
                lambda d: len(d.get("candidates", [])) >= 1,
            ],
            description="candidates present",
            timeout=15,
        )
    ))

    test("POST /api/basket-compare — 4 supplements", lambda: (
        _post_check(
            "/api/basket-compare",
            {"supplements": ["Iron", "CoQ10", "Zinc", "Vitamin C"]},
            checks=[
                lambda d: "winner_name" in d,
                lambda d: d.get("winner_total", 0) > 0,
                lambda d: len(d.get("retailer_totals", [])) >= 2,
            ],
            description="winner present, total > 0, ≥2 retailers",
            timeout=25,
        )
    ))

    test("POST /api/separation-schedule/from-golden-record", lambda: (
        _post_check(
            "/api/separation-schedule/from-golden-record",
            {"golden_record": {
                "product_name": "Vitamin D3 5000 IU",
                "brand": "NOW Foods",
                "audit": [{"name": "Cholecalciferol", "retail_amount": 125, "retail_unit": "mcg"}]
            }},
            checks=[lambda d: "blocks" in d],
            description="blocks present",
        )
    ))

    warn("POST /audit (Bright Data)", lambda: (
        _check_audit_available()
    ))

    return True


def _get(path: str) -> str:
    import urllib.request
    resp = urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5)
    assert resp.status == 200, f"HTTP {resp.status}"
    return "HTTP 200"


def _check_config() -> str:
    import urllib.request
    resp = urllib.request.urlopen(f"{BASE_URL}/config", timeout=5)
    data = json.loads(resp.read())
    assert data.get("supabase_url"), "supabase_url missing or empty"
    assert data.get("supabase_anon_key"), "supabase_anon_key missing or empty"
    url = data["supabase_url"]
    masked = url[:20] + "..." if len(url) > 20 else url
    return f"Supabase URL: {masked}"


def _post_check(
    path: str,
    payload: dict,
    checks: list[Callable],
    description: str,
    timeout: int = 10,
) -> str:
    import urllib.request
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(resp.read())
    assert "error" not in data, f"Server returned error: {data['error']}"
    for i, check in enumerate(checks):
        assert check(data), f"Check {i+1} failed. Response keys: {list(data.keys())}"
    return description


def _check_audit_available() -> str:
    import urllib.request
    body = json.dumps({"url": "https://www.iherb.com/pr/now-foods-vitamin-d-3-5-000-iu-240-softgels/14717"}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/audit",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        if data.get("error"):
            return f"Bright Data blocked: {str(data['error'])[:80]}"
        return f"Audit OK — {data.get('brand')} {data.get('product_name')}"
    except Exception as e:
        return f"Audit unavailable: {e}"


# ── PERFORMANCE TESTS ────────────────────────────────────────────────────────

def run_performance_tests():
    print("\n── Performance tests ────────────────────────────────────────────")

    def timed_post(path, payload, max_seconds):
        import urllib.request
        start = time.time()
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=max_seconds + 5)
        data = json.loads(resp.read())
        elapsed = round(time.time() - start, 2)
        assert "error" not in data, f"Error: {data.get('error')}"
        assert elapsed <= max_seconds, f"Too slow: {elapsed}s > {max_seconds}s limit"
        return f"{elapsed}s (limit {max_seconds}s)"

    test("Separation Coach response < 0.5s", lambda:
        timed_post("/api/separation-schedule",
            {"medications": ["Warfarin", "Atorvastatin"],
             "supplements": ["Magnesium Glycinate", "Vitamin D3", "Omega-3"]},
            max_seconds=0.5))

    test("Med Check response < 0.3s", lambda:
        timed_post("/med-check",
            {"medications": ["warfarin"], "supplements": ["vitamin k2"]},
            max_seconds=0.3))

    warn("Basket Compare response < 8s", lambda:
        timed_post("/api/basket-compare",
            {"supplements": ["Iron", "CoQ10", "Zinc", "Vitamin C"]},
            max_seconds=8))


# ── CONTENT / SAFETY TESTS ───────────────────────────────────────────────────

def run_content_tests():
    print("\n── Content / safety tests ───────────────────────────────────────")

    def check_html_contains(path, required_phrases):
        import urllib.request
        resp = urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5)
        html = resp.read().decode("utf-8", errors="ignore").lower()
        missing = [p for p in required_phrases if p.lower() not in html]
        assert not missing, f"Missing from {path}: {missing}"
        return f"All {len(required_phrases)} phrases found"

    def check_html_not_contains(path, banned_phrases):
        import urllib.request
        resp = urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5)
        html = resp.read().decode("utf-8", errors="ignore").lower()
        found = [p for p in banned_phrases if p.lower() in html]
        assert not found, f"Banned phrases found in {path}: {found}"
        return f"None of {len(banned_phrases)} banned phrases found"

    test("Main app has medical disclaimer", lambda:
        check_html_contains("/", [
            "not medical advice",
            "follow your prescription",
        ]))

    test("Main app has affiliate disclosure", lambda:
        check_html_contains("/", [
            "commission",
        ]))

    test("Main app has no banned claims", lambda:
        check_html_not_contains("/", [
            "fda approved",
            "clinically proven",
            "replaces your doctor",
            "guaranteed safe",
        ]))


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    _safe_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="Run engine + endpoint + performance + content tests")
    parser.add_argument("--endpoints", action="store_true",
                        help="Run endpoint tests only (server must be running)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Elthio Pre-Launch Health Check")
    print("=" * 60)

    run_engine_tests()

    if args.full or args.endpoints:
        server_ok = run_endpoint_tests()
        if server_ok and args.full:
            run_performance_tests()
            run_content_tests()
        if not server_ok and args.endpoints:
            print(f"\n{FAIL} Endpoint tests requested but server is not reachable.")
            sys.exit(1)

    passed = [r for r in results if r["status"] == "pass"]
    failed = [r for r in results if r["status"] in ("fail", "error")]
    critical_fails = [r for r in failed if r.get("critical", True)]

    print("\n" + "=" * 60)
    print(f"  Results: {len(passed)} passed, {len(failed)} failed")
    print("=" * 60)

    if failed:
        print("\nFailed tests:")
        for r in failed:
            crit = " [CRITICAL]" if r.get("critical", True) else " [warning]"
            print(f"  {FAIL}  {r['name']}{crit}")
            print(f"       {r['msg']}")

    if not critical_fails:
        print(f"\n{PASS} All critical tests passed — ready to deploy Elthio.")
    else:
        print(f"\n{FAIL} {len(critical_fails)} critical test(s) failed — fix before deploying.")
        sys.exit(1)


if __name__ == "__main__":
    main()

