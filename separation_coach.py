"""
Separation Coach — build daily timing schedules from meds, supplements, and rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rules import BLOCK_SORT, RULES, STRENGTH_CRITICAL, STRENGTH_ORDER, TIME_BLOCK_META, TimeBlock


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s'\.]", " ", (text or "").lower())).strip()


def _matches_any(text: str, keywords: list[str]) -> bool:
    n = _normalize(text)
    if not n:
        return False
    for k in keywords:
        kn = _normalize(k)
        if kn and (kn in n or n in kn):
            return True
    return False


def _med_label(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("name") or item.get("medication") or item.get("label") or "").strip()
    return str(item or "").strip()


def _supp_label(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        parts = [item.get("name"), item.get("brand"), item.get("product_name")]
        return " ".join(str(p) for p in parts if p).strip() or str(item.get("ingredients") or "")[:120]
    return str(item or "").strip()


def _supp_search_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return " ".join(
            str(item.get(k) or "")
            for k in ("name", "brand", "product_name", "ingredients", "form")
        )
    return str(item or "")


def _block_time(block_id: str, user_routine: dict | None) -> str:
    routine = user_routine or {}
    mapping = {
        TimeBlock.EMPTY_STOMACH.value: routine.get("wake_time"),
        TimeBlock.MORNING.value: routine.get("breakfast"),
        TimeBlock.MIDDAY.value: routine.get("lunch"),
        TimeBlock.EVENING.value: routine.get("dinner"),
        TimeBlock.BEDTIME.value: routine.get("bedtime"),
        TimeBlock.FATTY_MEAL.value: routine.get("dinner"),
        TimeBlock.FLEXIBLE.value: routine.get("breakfast"),
    }
    t = mapping.get(block_id)
    if t:
        return str(t)[:5]
    return TIME_BLOCK_META.get(block_id, {}).get("default_time", "09:00")


def _earlier_block(a: str, b: str) -> str:
    flex = TimeBlock.FLEXIBLE.value
    if a == flex:
        return b
    if b == flex:
        return a
    return a if BLOCK_SORT.get(a, 99) <= BLOCK_SORT.get(b, 99) else b


def _later_block(a: str, b: str) -> str:
    flex = TimeBlock.FLEXIBLE.value
    if a == flex:
        return b
    if b == flex:
        return a
    return a if BLOCK_SORT.get(a, 99) >= BLOCK_SORT.get(b, 99) else b


@dataclass
class ScheduleItem:
    kind: str  # "rx" | "supplement"
    name: str
    instruction: str
    strength: str
    rule_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "instruction": self.instruction,
            "strength": self.strength,
            "rule_id": self.rule_id,
        }


@dataclass
class SeparationScheduleResult:
    blocks: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    unmatched: dict = field(default_factory=lambda: {"medications": [], "supplements": []})
    active_rules: list[dict] = field(default_factory=list)
    synergy_suggestions: list[dict] = field(default_factory=list)
    disclaimer: str = (
        "Educational timing guide only — not medical advice. "
        "Always follow your prescription label and pharmacist instructions."
    )
    rules_matched: int = 0

    def to_json(self) -> dict:
        return {
            "blocks": self.blocks,
            "conflicts": self.conflicts,
            "unmatched": self.unmatched,
            "active_rules": self.active_rules,
            "synergy_suggestions": self.synergy_suggestions,
            "disclaimer": self.disclaimer,
            "rules_matched": self.rules_matched,
        }

    def to_json_str(self) -> str:
        return json.dumps(self.to_json(), indent=2)


def generate_separation_schedule(
    meds: list[Any],
    supplements: list[Any],
    user_routine: dict | None = None,
) -> SeparationScheduleResult:
    medications = [_med_label(m) for m in meds if _med_label(m)]
    supps_raw = [s for s in supplements if _supp_search_text(s).strip()]

    med_assign: dict[str, dict] = {}
    supp_assign: dict[str, dict] = {}
    active_rules: list[dict] = []

    for rule in RULES:
        med_kw = rule.get("med_keywords") or []
        supp_kw = rule.get("supp_keywords") or []
        supp_only = bool(rule.get("supp_only"))
        med_only = bool(rule.get("med_only")) or not supp_kw

        # Rules with no med_keywords fire on supplement name alone
        if not med_kw and supp_kw:
            matched_supps_direct: list[str] = []
            for s in supps_raw:
                text = _supp_search_text(s)
                if _matches_any(text, supp_kw):
                    label = _supp_label(s) or text
                    if label and label not in matched_supps_direct:
                        matched_supps_direct.append(label)
            if matched_supps_direct:
                active_rules.append(
                    {
                        **{
                            k: rule[k]
                            for k in rule
                            if k not in ("med_keywords", "supp_keywords")
                        },
                        "matched_meds": [],
                        "matched_supps": matched_supps_direct,
                    }
                )
                strength = rule.get("strength") or "STANDARD"
                supp_block = rule.get("supp_block") or TimeBlock.FLEXIBLE.value
                rid = rule.get("id")
                for label in matched_supps_direct:
                    entry = supp_assign.setdefault(
                        label,
                        {
                            "block": supp_block,
                            "strength": strength,
                            "instructions": [],
                            "rule_ids": [],
                        },
                    )
                    entry["block"] = _later_block(entry["block"], supp_block)
                    if STRENGTH_ORDER.get(strength, 9) < STRENGTH_ORDER.get(
                        entry["strength"], 9
                    ):
                        entry["strength"] = strength
                    ins = rule.get("instruction_supp") or rule.get("title") or ""
                    if ins and ins not in entry["instructions"]:
                        entry["instructions"].append(ins)
                    if rid and rid not in entry["rule_ids"]:
                        entry["rule_ids"].append(rid)
            continue

        matched_meds: list[str] = []
        matched_supps: list[str] = []

        if supp_only:
            if not supp_kw:
                continue
            for s in supps_raw:
                text = _supp_search_text(s)
                if _matches_any(text, supp_kw):
                    label = _supp_label(s) or text
                    if label and label not in matched_supps:
                        matched_supps.append(label)
            if not matched_supps:
                continue
        elif med_only:
            matched_meds = [m for m in medications if _matches_any(m, med_kw)]
            if not matched_meds:
                continue
        else:
            matched_meds = [m for m in medications if _matches_any(m, med_kw)]
            if not matched_meds:
                continue
            for s in supps_raw:
                text = _supp_search_text(s)
                if _matches_any(text, supp_kw):
                    label = _supp_label(s) or text
                    if label and label not in matched_supps:
                        matched_supps.append(label)
            if not matched_supps:
                continue

        active_rules.append(
            {
                **{k: rule[k] for k in rule if k != "med_keywords" and k != "supp_keywords"},
                "matched_meds": matched_meds,
                "matched_supps": matched_supps,
            }
        )

        strength = rule.get("strength") or "STANDARD"
        med_block = rule.get("med_block") or TimeBlock.FLEXIBLE.value
        supp_block = rule.get("supp_block") or TimeBlock.FLEXIBLE.value
        hours = rule.get("separation_hours") or 0

        for m in matched_meds:
            entry = med_assign.setdefault(
                m,
                {"block": med_block, "strength": strength, "instructions": [], "rule_ids": []},
            )
            entry["block"] = _earlier_block(entry["block"], med_block)
            if STRENGTH_ORDER.get(strength, 9) < STRENGTH_ORDER.get(entry["strength"], 9):
                entry["strength"] = strength
            ins = rule.get("instruction_med") or rule.get("title") or ""
            if ins and ins not in entry["instructions"]:
                entry["instructions"].append(ins)
            rid = rule.get("id")
            if rid and rid not in entry["rule_ids"]:
                entry["rule_ids"].append(rid)
            if hours:
                sep = f"Keep ~{hours}h apart from matched supplements"
                if sep not in entry["instructions"]:
                    entry["instructions"].append(sep)

        if rule.get("annotate_all_supplements"):
            for s in supps_raw:
                label = _supp_label(s)
                if not label:
                    continue
                entry = supp_assign.setdefault(
                    label,
                    {"block": supp_block, "strength": strength, "instructions": [], "rule_ids": []},
                )
                entry["block"] = _later_block(entry["block"], supp_block)
                ins = rule.get("instruction_supp") or rule.get("title") or ""
                if ins and ins not in entry["instructions"]:
                    entry["instructions"].append(ins)
        elif matched_supps:
            for label in matched_supps:
                entry = supp_assign.setdefault(
                    label,
                    {"block": supp_block, "strength": strength, "instructions": [], "rule_ids": []},
                )
                entry["block"] = _later_block(entry["block"], supp_block)
                if STRENGTH_ORDER.get(strength, 9) < STRENGTH_ORDER.get(entry["strength"], 9):
                    entry["strength"] = strength
                ins = rule.get("instruction_supp") or rule.get("title") or ""
                if ins and ins not in entry["instructions"]:
                    entry["instructions"].append(ins)

    # Conflicts: same item assigned to blocks that are too close
    conflicts: list[dict] = []
    for rule in active_rules:
        if (rule.get("separation_hours") or 0) > 0 and rule.get("matched_meds") and rule.get("matched_supps"):
            conflicts.append(
                {
                    "title": rule.get("title"),
                    "strength": rule.get("strength"),
                    "detail": rule.get("instruction_supp") or rule.get("instruction_med"),
                    "separation_hours": rule.get("separation_hours"),
                    "medications": rule.get("matched_meds"),
                    "supplements": rule.get("matched_supps"),
                }
            )

    timeline: dict[str, list[ScheduleItem]] = {bid: [] for bid in TIME_BLOCK_META}
    for med, info in med_assign.items():
        timeline[info["block"]].append(
            ScheduleItem(
                kind="rx",
                name=med,
                instruction=" · ".join(info["instructions"]) or "Take as prescribed",
                strength=info["strength"],
                rule_id=(info["rule_ids"][0] if info["rule_ids"] else None),
            )
        )

    for label, info in supp_assign.items():
        timeline[info["block"]].append(
            ScheduleItem(
                kind="supplement",
                name=label,
                instruction=" · ".join(info["instructions"]) or "Take as directed on label",
                strength=info["strength"],
                rule_id=(info["rule_ids"][0] if info["rule_ids"] else None),
            )
        )

    unmatched_meds = [m for m in medications if m not in med_assign]
    unmatched_supps = []
    for s in supps_raw:
        label = _supp_label(s)
        if label and label not in supp_assign:
            unmatched_supps.append(label)

    for m in unmatched_meds:
        timeline[TimeBlock.FLEXIBLE.value].append(
            ScheduleItem(
                kind="rx",
                name=m,
                instruction="No curated timing rule — follow your prescription label",
                strength="STANDARD",
            )
        )
    for s in unmatched_supps:
        timeline[TimeBlock.FLEXIBLE.value].append(
            ScheduleItem(
                kind="supplement",
                name=s,
                instruction="No curated timing rule — take when you will remember daily",
                strength="STANDARD",
            )
        )

    blocks: list[dict] = []
    for block_id in sorted(TIME_BLOCK_META.keys(), key=lambda x: BLOCK_SORT.get(x, 99)):
        items = timeline.get(block_id) or []
        if not items:
            continue
        meta = TIME_BLOCK_META[block_id]
        blocks.append(
            {
                "id": block_id,
                "label": meta["label"],
                "icon": meta.get("icon", ""),
                "time": _block_time(block_id, user_routine),
                "items": [i.to_dict() for i in items],
                "has_critical": any(i.strength == STRENGTH_CRITICAL for i in items),
            }
        )

    synergy_suggestions = get_synergy_suggestions(supplements, meds)

    return SeparationScheduleResult(
        blocks=blocks,
        conflicts=conflicts,
        unmatched={"medications": unmatched_meds, "supplements": unmatched_supps},
        active_rules=active_rules,
        synergy_suggestions=synergy_suggestions,
        rules_matched=len(active_rules),
    )


SYNERGY_SUGGESTIONS: list[dict] = [
    {
        "if_present": ["vitamin d", "cholecalciferol", "vitamin d3"],
        "if_missing": [
            "vitamin k",
            "vitamin k2",
            "mk-7",
            "mk-4",
            "menaquinone",
            "d and k",
            "vitamins d and k",
        ],
        "suggestion": (
            "You take Vitamin D3 but not Vitamin K2. D3 increases calcium absorption — "
            "K2 directs that calcium into bones instead of arteries. "
            "Long-term D3 without K2 may cause calcium to deposit in soft tissue."
        ),
        "type": "pairing",
    },
    {
        "if_present": ["vitamin d", "cholecalciferol", "vitamin d3"],
        "if_missing": ["magnesium"],
        "suggestion": (
            "You take Vitamin D3 but not Magnesium. Magnesium is required to convert "
            "D3 into its active form — without enough magnesium, supplemental D3 "
            "may remain largely inactive."
        ),
        "type": "pairing",
    },
    {
        "if_present": ["iron", "ferrous"],
        "if_missing": ["vitamin c", "ascorbic acid"],
        "suggestion": (
            "You take iron but not Vitamin C. Taking vitamin C alongside iron "
            "increases absorption up to 3x — especially important for plant-based iron."
        ),
        "type": "pairing",
    },
    {
        "if_present": ["zinc"],
        "if_missing": ["copper"],
        "suggestion": (
            "You take zinc but not copper. High zinc intake (40mg+) depletes copper "
            "over time. A small copper supplement (1–2mg) is commonly recommended "
            "alongside long-term zinc use."
        ),
        "type": "caution",
    },
    {
        "if_present": ["collagen", "collagen peptides"],
        "if_missing": ["vitamin c", "ascorbic acid"],
        "suggestion": (
            "You take collagen but not Vitamin C. Vitamin C is required for collagen "
            "synthesis — without it, collagen supplements are significantly less effective."
        ),
        "type": "pairing",
    },
    {
        "if_present": ["curcumin", "turmeric"],
        "if_missing": ["black pepper", "piperine", "bioperine"],
        "suggestion": (
            "You take curcumin or turmeric. Without piperine (black pepper extract), "
            "curcumin absorption is very poor. Look for a formula that includes "
            "BioPerine, or take it with a meal that includes black pepper."
        ),
        "type": "caution",
    },
    {
        "id": "omega-vitamin-e-pairing",
        "if_present": ["omega-3", "fish oil", "epa", "dha"],
        "if_missing": ["vitamin e", "tocopherol", "mixed tocopherols"],
        "skip_if_meds": ["warfarin", "coumadin", "jantoven"],
        "suggestion": (
            "You take omega-3 fish oil. Vitamin E helps protect omega-3 fatty acids "
            "from oxidation in the body. Many quality fish oil products include "
            "vitamin E for this reason — worth checking your label."
        ),
        "type": "pairing",
    },
    {
        "if_present": ["5-htp", "hydroxytryptophan"],
        "if_missing": [],
        "always_show": True,
        "suggestion": (
            "You take 5-HTP. Do not combine with SSRIs, SNRIs, or MAOIs — "
            "this combination can cause serotonin syndrome, a serious condition. "
            "If you take any antidepressants, stop 5-HTP and speak to your doctor."
        ),
        "type": "caution",
    },
    {
        "if_present": ["melatonin"],
        "if_missing": ["magnesium"],
        "suggestion": (
            "You take melatonin. Magnesium glycinate at bedtime pairs well with "
            "melatonin — it supports deeper sleep and muscle relaxation without "
            "the grogginess some people get from melatonin alone."
        ),
        "type": "pairing",
    },
]


def get_synergy_suggestions(
    supplements: list[Any],
    medications: list[Any] | None = None,
) -> list[dict]:
    """
    Compare the supplement list against known synergy pairs.
    Returns suggestions for missing pairings or important cautions.
    """
    all_text = " ".join(
        _normalize(_supp_search_text(s))
        for s in supplements
        if _supp_search_text(s).strip()
    )
    med_labels = [_normalize(_med_label(m)) for m in (medications or []) if _med_label(m)]

    results: list[dict] = []
    for rule in SYNERGY_SUGGESTIONS:
        present = rule.get("if_present", [])
        missing = rule.get("if_missing", [])
        always = rule.get("always_show", False)
        skip_meds = rule.get("skip_if_meds") or []

        if skip_meds and any(_matches_any(m, skip_meds) for m in med_labels):
            continue

        has_present = _matches_any(all_text, present) if present else False
        if not has_present:
            continue

        if always:
            results.append(
                {
                    "type": rule["type"],
                    "suggestion": rule["suggestion"],
                }
            )
            continue

        has_missing = any(
            _matches_any(all_text, [kw]) or _normalize(kw) in all_text for kw in missing
        )
        if not has_missing:
            results.append(
                {
                    "type": rule["type"],
                    "suggestion": rule["suggestion"],
                }
            )

    return results


def schedule_from_golden_record(
    golden_record: dict,
    medications: list[Any] | None = None,
    user_routine: dict | None = None,
) -> SeparationScheduleResult:
    """Build schedule from one golden record audit + optional Rx list."""
    meds = list(medications or [])
    supps: list[dict] = []

    name = golden_record.get("product_name") or golden_record.get("name")
    brand = golden_record.get("brand") or ""
    audit = golden_record.get("audit") or []
    ingredients = ", ".join(
        f"{a.get('name', '')} {a.get('retail_amount', '')}{a.get('retail_unit', '')}".strip()
        for a in audit
        if isinstance(a, dict) and a.get("name")
    )
    if name:
        supps.append(
            {
                "name": name,
                "brand": brand,
                "ingredients": ingredients,
                "source": "golden_record",
            }
        )

    return generate_separation_schedule(meds, supps, user_routine)


if __name__ == "__main__":
    tests = [
        {
            "label": "Supplement-only — Vitamin D + B + C + Biotin + Ginseng",
            "meds": [],
            "supps": [
                "Vitamin D3",
                "Vitamin B Complex",
                "Vitamin C",
                "Biotin",
                "Ginseng",
            ],
            "expect_blocks": ["morning", "midday", "fatty_meal"],
            "expect_synergy": True,
            "expect_unmatched": 0,
        },
        {
            "label": "Warfarin stack — existing rules still work",
            "meds": ["Warfarin", "Atorvastatin"],
            "supps": [
                {"name": "Vitamin D and K with Sea-Iodine"},
                {"name": "Omega-3 Fish Oil 1000mg"},
                {"name": "Magnesium Glycinate"},
            ],
            "expect_blocks": ["evening", "bedtime", "fatty_meal"],
            "expect_synergy": False,
            "expect_unmatched": 0,
        },
        {
            "label": "Iron without Vitamin C — synergy suggestion fires",
            "meds": [],
            "supps": ["Iron Bisglycinate", "Zinc Picolinate"],
            "expect_blocks": ["empty_stomach", "morning"],
            "expect_synergy": True,
            "expect_unmatched": 0,
        },
        {
            "label": "5-HTP bedtime — always-show caution fires",
            "meds": [],
            "supps": ["5-HTP", "Melatonin", "Magnesium Glycinate"],
            "expect_blocks": ["bedtime"],
            "expect_synergy": True,
            "expect_unmatched": 0,
        },
        {
            "label": "Curcumin without piperine — caution fires",
            "meds": [],
            "supps": ["Turmeric Curcumin 500mg"],
            "expect_blocks": ["fatty_meal"],
            "expect_synergy": True,
            "expect_unmatched": 0,
        },
    ]

    all_passed = True
    for t in tests:
        result = generate_separation_schedule(t["meds"], t["supps"])
        j = result.to_json()
        block_ids = [b["id"] for b in j["blocks"]]
        has_synergy = len(j["synergy_suggestions"]) > 0
        unmatched_count = (
            len(j["unmatched"]["medications"]) + len(j["unmatched"]["supplements"])
        )
        blocks_ok = all(b in block_ids for b in t["expect_blocks"])
        synergy_ok = has_synergy == t["expect_synergy"]
        unmatched_ok = unmatched_count == t["expect_unmatched"]
        passed = blocks_ok and synergy_ok and unmatched_ok
        if not passed:
            all_passed = False
        status = "PASS" if passed else "FAIL"
        print(f"{status}  {t['label']}")
        print(f"     blocks:    {block_ids}")
        print(f"     rules:     {j['rules_matched']}")
        print(f"     unmatched: {unmatched_count}")
        print(f"     synergy:   {len(j['synergy_suggestions'])} suggestion(s)")
        for s in j["synergy_suggestions"]:
            print(f"       [{s['type']}] {s['suggestion'][:70]}...")
        print()

    print("All tests passed" if all_passed else "SOME TESTS FAILED")
