"""
stack_tracker.py — Elthio
=======================================
Tracks a user's supplement stack, detects duplicates,
warns on dose limits, totals daily intake, and flags
cheaper alternatives.

Usage:
    from stack_tracker import StackTracker
    tracker = StackTracker()
    tracker.add_product("golden_record.json")
    report = tracker.analyze()
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

# ---------------------------------------------------------------------------
# NIH Tolerable Upper Intake Levels (UL) per day
# Source: NIH Office of Dietary Supplements
# Units normalized to mg where possible
# ---------------------------------------------------------------------------
UPPER_LIMITS_MG: dict[str, float] = {
    "vitamin a":        3.0,        # 3000 mcg RAE = 3mg
    "vitamin b3":       35.0,       # niacin 35mg
    "vitamin b6":       100.0,
    "vitamin c":        2000.0,
    "vitamin d":        100.0,      # 4000 IU ≈ 100 mcg = 0.1mg — stored as mcg below
    "vitamin d3":       100.0,
    "vitamin e":        1000.0,
    "vitamin k":        None,       # no established UL
    "folate":           1.0,        # 1000 mcg = 1mg
    "folic acid":       1.0,
    "calcium":          2500.0,
    "iron":             45.0,
    "magnesium":        350.0,      # from supplements only
    "zinc":             40.0,
    "selenium":         0.4,        # 400 mcg = 0.4mg
    "iodine":           1.1,        # 1100 mcg
    "copper":           10.0,
    "manganese":        11.0,
    "molybdenum":       2.0,
    "boron":            20.0,
    "nickel":           1.0,
    "vanadium":         1.8,
}

# IU to mcg conversions for vitamins where needed
IU_TO_MCG: dict[str, float] = {
    "vitamin d":  0.025,   # 1 IU = 0.025 mcg
    "vitamin d3": 0.025,
    "vitamin a":  0.3,     # 1 IU retinol = 0.3 mcg RAE
    "vitamin e":  0.67,    # 1 IU = 0.67 mg alpha-tocopherol
}

UNIT_TO_MG: dict[str, float] = {
    "mg":  1.0,
    "g":   1000.0,
    "mcg": 0.001,
    "ug":  0.001,
    "iu":  None,   # handled per-ingredient via IU_TO_MCG
    "%":   None,   # cannot normalize
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class StackIngredient:
    name: str
    amount_mg: Optional[float]      # normalized to mg
    raw_amount: Optional[float]
    raw_unit: Optional[str]
    source_product: str


@dataclass
class DailyTotal:
    name: str
    total_mg: Optional[float]
    upper_limit_mg: Optional[float]
    sources: list[str]
    status: str   # OK | WARNING | EXCEEDED | UNKNOWN


@dataclass
class DuplicateAlert:
    ingredient: str
    products: list[str]
    total_mg: Optional[float]


@dataclass
class StackReport:
    products: list[str]
    daily_totals: list[DailyTotal]
    duplicates: list[DuplicateAlert]
    warnings: list[str]
    total_ingredients: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Stack Tracker
# ---------------------------------------------------------------------------

class StackTracker:
    """
    Maintains a user's supplement stack and analyzes it for
    duplicates, dose limits, and daily totals.
    """

    STACK_FILE = Path("stack.json")
    FUZZY_THRESHOLD = 80

    def __init__(self):
        self._stack: dict[str, list[StackIngredient]] = {}  # product_name → ingredients
        self._load()

    # ── Persistence ────────────────────────────────────────────────────────

    def _load(self):
        if self.STACK_FILE.exists():
            data = json.loads(self.STACK_FILE.read_text(encoding="utf-8"))
            for product, ings in data.items():
                self._stack[product] = [StackIngredient(**i) for i in ings]

    def _save(self):
        data = {
            product: [asdict(i) for i in ings]
            for product, ings in self._stack.items()
        }
        self.STACK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Public API ─────────────────────────────────────────────────────────

    def add_from_golden_record(self, path: str) -> str:
        """Load a golden_record.json and add it to the stack."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        product_name = f"{data.get('brand', 'Unknown')} — {data.get('product_name', 'Unknown')}"

        ingredients: list[StackIngredient] = []
        for entry in data.get("audit", []):
            if entry.get("retail_amount") is None:
                continue
            name = entry["name"]
            amount = entry.get("retail_amount")
            unit = entry.get("retail_unit")
            amount_mg = _normalize_to_mg(name, amount, unit)
            ingredients.append(StackIngredient(
                name=name,
                amount_mg=amount_mg,
                raw_amount=amount,
                raw_unit=unit,
                source_product=product_name,
            ))

        self._stack[product_name] = ingredients
        self._save()
        return product_name

    def add_manual(self, product_name: str, ingredients: list[dict]) -> None:
        """
        Manually add a product to the stack.
        ingredients: [{"name": "Vitamin C", "amount": 500, "unit": "mg"}, ...]
        """
        ings = []
        for ing in ingredients:
            name = ing["name"]
            amount = ing.get("amount")
            unit = ing.get("unit")
            ings.append(StackIngredient(
                name=name,
                amount_mg=_normalize_to_mg(name, amount, unit),
                raw_amount=amount,
                raw_unit=unit,
                source_product=product_name,
            ))
        self._stack[product_name] = ings
        self._save()

    def remove_product(self, product_name: str) -> bool:
        if product_name in self._stack:
            del self._stack[product_name]
            self._save()
            return True
        return False

    def list_products(self) -> list[str]:
        return list(self._stack.keys())

    def clear(self):
        self._stack = {}
        self._save()

    def analyze(self) -> StackReport:
        """Run full stack analysis. Returns StackReport."""
        all_ingredients: list[StackIngredient] = []
        for ings in self._stack.values():
            all_ingredients.extend(ings)

        daily_totals = _compute_daily_totals(all_ingredients)
        duplicates = _detect_duplicates(all_ingredients, self.FUZZY_THRESHOLD)
        warnings = _build_warnings(daily_totals, duplicates)

        return StackReport(
            products=self.list_products(),
            daily_totals=daily_totals,
            duplicates=duplicates,
            warnings=warnings,
            total_ingredients=len(set(i.name.lower() for i in all_ingredients)),
        )


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _normalize_to_mg(
    name: str,
    amount: Optional[float],
    unit: Optional[str],
) -> Optional[float]:
    if amount is None or unit is None:
        return None
    unit = unit.lower().strip()
    name_lower = name.lower()

    if unit == "iu":
        for key, factor in IU_TO_MCG.items():
            if key in name_lower:
                return amount * factor * 0.001  # mcg → mg
        return None  # unknown IU conversion

    factor = UNIT_TO_MG.get(unit)
    if factor is None:
        return None
    return amount * factor


def _compute_daily_totals(ingredients: list[StackIngredient]) -> list[DailyTotal]:
    """Group by ingredient name (fuzzy), sum amounts, check UL."""
    groups: dict[str, list[StackIngredient]] = {}
    canonical: dict[str, str] = {}  # lower_name → canonical display name

    for ing in ingredients:
        key = ing.name.lower()
        matched = None

        if groups:
            result = process.extractOne(
                key,
                list(groups.keys()),
                scorer=fuzz.token_sort_ratio,
            )
            if result and result[1] >= 80:
                matched = result[0]

        if matched:
            groups[matched].append(ing)
        else:
            groups[key] = [ing]
            canonical[key] = ing.name

    totals: list[DailyTotal] = []
    for key, ings in groups.items():
        display_name = canonical.get(key, ings[0].name)
        amounts = [i.amount_mg for i in ings if i.amount_mg is not None]
        total_mg = sum(amounts) if amounts else None
        sources = list({i.source_product for i in ings})

        ul = None
        for ul_key, ul_val in UPPER_LIMITS_MG.items():
            if ul_key in key or key in ul_key:
                ul = ul_val
                break

        if total_mg is None:
            status = "UNKNOWN"
        elif ul is None:
            status = "OK"
        elif total_mg > ul:
            status = "EXCEEDED"
        elif total_mg > ul * 0.8:
            status = "WARNING"
        else:
            status = "OK"

        totals.append(DailyTotal(
            name=display_name,
            total_mg=round(total_mg, 3) if total_mg else None,
            upper_limit_mg=ul,
            sources=sources,
            status=status,
        ))

    return sorted(totals, key=lambda x: (x.status != "EXCEEDED", x.status != "WARNING", x.name))


def _detect_duplicates(
    ingredients: list[StackIngredient],
    threshold: int,
) -> list[DuplicateAlert]:
    """Find ingredients appearing in 2+ products."""
    groups: dict[str, list[StackIngredient]] = {}

    for ing in ingredients:
        key = ing.name.lower()
        matched = None
        if groups:
            result = process.extractOne(
                key, list(groups.keys()), scorer=fuzz.token_sort_ratio
            )
            if result and result[1] >= threshold:
                matched = result[0]
        if matched:
            groups[matched].append(ing)
        else:
            groups[key] = [ing]

    duplicates = []
    for key, ings in groups.items():
        products = list({i.source_product for i in ings})
        if len(products) > 1:
            amounts = [i.amount_mg for i in ings if i.amount_mg is not None]
            duplicates.append(DuplicateAlert(
                ingredient=ings[0].name,
                products=products,
                total_mg=round(sum(amounts), 3) if amounts else None,
            ))

    return duplicates


def _build_warnings(
    totals: list[DailyTotal],
    duplicates: list[DuplicateAlert],
) -> list[str]:
    warnings = []
    for t in totals:
        if t.status == "EXCEEDED":
            warnings.append(
                f"⚠️  {t.name}: {t.total_mg}mg exceeds NIH upper limit of {t.upper_limit_mg}mg/day"
            )
        elif t.status == "WARNING":
            warnings.append(
                f"⚡ {t.name}: {t.total_mg}mg is approaching NIH upper limit of {t.upper_limit_mg}mg/day"
            )
    for d in duplicates:
        warnings.append(
            f"🔁 {d.ingredient} appears in {len(d.products)} products: {', '.join(d.products)}"
        )
    return warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tracker = StackTracker()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python stack_tracker.py add <golden_record.json>")
        print("  python stack_tracker.py list")
        print("  python stack_tracker.py analyze")
        print("  python stack_tracker.py remove <product_name>")
        print("  python stack_tracker.py clear")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: python stack_tracker.py add <golden_record.json>")
            sys.exit(1)
        name = tracker.add_from_golden_record(sys.argv[2])
        print(f"✅ Added: {name}")

    elif cmd == "list":
        products = tracker.list_products()
        if not products:
            print("Stack is empty.")
        else:
            print(f"\n{len(products)} product(s) in your stack:\n")
            for p in products:
                print(f"  • {p}")

    elif cmd == "analyze":
        report = tracker.analyze()
        if not report.products:
            print("Stack is empty. Add products first.")
            sys.exit(0)

        print(f"\n{'='*65}")
        print(f"  ELTHIO STACK ANALYSIS")
        print(f"{'='*65}")
        print(f"  Products in stack : {len(report.products)}")
        print(f"  Unique ingredients: {report.total_ingredients}")
        print(f"{'='*65}")

        if report.warnings:
            print(f"\n  ALERTS:")
            for w in report.warnings:
                print(f"    {w}")

        print(f"\n  DAILY TOTALS:")
        print(f"  {'STATUS':<10} {'INGREDIENT':<30} {'TOTAL':>10}  {'UL':>10}")
        print(f"  {'-'*65}")
        icons = {"OK": "✅", "WARNING": "⚡", "EXCEEDED": "❌", "UNKNOWN": "❓"}
        for t in report.daily_totals:
            icon = icons.get(t.status, "?")
            total = f"{t.total_mg}mg" if t.total_mg else "N/A"
            ul = f"{t.upper_limit_mg}mg" if t.upper_limit_mg else "No UL"
            print(f"  {icon} {t.status:<8} {t.name:<30} {total:>10}  {ul:>10}")

        if report.duplicates:
            print(f"\n  DUPLICATE INGREDIENTS:")
            for d in report.duplicates:
                print(f"    🔁 {d.ingredient} ({d.total_mg}mg total)")
                for p in d.products:
                    print(f"       • {p}")

        print(f"\n{'='*65}\n")

    elif cmd == "remove":
        if len(sys.argv) < 3:
            print("Usage: python stack_tracker.py remove <product_name>")
            sys.exit(1)
        name = " ".join(sys.argv[2:])
        if tracker.remove_product(name):
            print(f"✅ Removed: {name}")
        else:
            print(f"❌ Not found: {name}")
            print("Run 'python stack_tracker.py list' to see product names.")

    elif cmd == "clear":
        tracker.clear()
        print("✅ Stack cleared.")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
