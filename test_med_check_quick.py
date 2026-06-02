"""Offline med-check smoke test (no RxNorm network)."""
import med_check_engine as m

m.lookup_rxnorm = lambda name, timeout=0: None  # noqa: ARG001

r = m.run_med_check(["warfarin"], ["vitamin k"])
assert r["interactions"], "warfarin + vitamin k should match"
assert r["interactions"][0]["severity"] == "critical", r["interactions"][0]

r2 = m.run_med_check(["metformin"], ["vitamin k2"])
assert not r2["interactions"], "metformin + k2 should not directly match"
assert r2["near_misses"], "should have near-miss for metformin"
assert any("B12" in x or "b12" in x.lower() for x in r2["near_misses"]), r2["near_misses"]

print("OK", len(r["interactions"]), r["interactions"][0]["severity"])
print("OK near_miss", len(r2["near_misses"]))
