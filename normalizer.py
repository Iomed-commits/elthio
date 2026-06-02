"""
normalizer.py — Parse supplement ingredient lines and normalize nutrient amounts
for Bio-Logic / NIH-style comparison (mcg, mg, IU where applicable).

Uses converters.normalize_nutrient for Vitamin D / Vitamin A conversions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from converters import normalize_nutrient

# Typical patterns: "125 mcg", "5,000 IU", "300 mg", "10 mg (22% DV)"
_AMOUNT_UNIT = re.compile(
    r"""
    (?P<amount>[\d,]+\.?\d*)\s*
    (?P<unit>mcg|µg|mg|g|IU|iu|mcL|mL|IU\b|%)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_amount_unit(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract first numeric amount + unit from a string."""
    text = text.replace(",", "")
    m = _AMOUNT_UNIT.search(text)
    if not m:
        return None, None
    try:
        amount = float(m.group("amount").replace(",", ""))
    except ValueError:
        return None, None
    unit = m.group("unit").lower()
    if unit in ("iu",):
        unit = "iu"
    return amount, unit


def strip_parenthetical_forms(name: str) -> str:
    """Keep main ingredient name; trim trailing parenthetical for matching."""
    name = name.strip()
    # Remove trailing "(as ...)" for nutrient name checks only if needed
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() or name


def normalize_line(
    line: str,
    nutrient_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse one ingredient / supplement-facts line and return structured + normalized data.

    Example line: "Vitamin D (as D3 Cholecalciferol) 125 mcg (5,000 IU)"
    """
    line = line.strip()
    if not line:
        return {"raw": line, "error": "empty"}

    amount, unit = parse_amount_unit(line)
    name_part = line
    m = _AMOUNT_UNIT.search(line.replace(",", ""))
    if m:
        name_part = line[: m.start()].strip()

    nutrient_for_conv = nutrient_hint or name_part
    result: Dict[str, Any] = {
        "raw": line,
        "name": name_part or line,
        "amount": amount,
        "unit": unit,
    }

    if amount is not None and unit:
        conv = normalize_nutrient(amount, unit, nutrient_for_conv)
        result["normalized"] = conv
    else:
        result["normalized"] = {"status": "no_numeric_amount", "raw": line}

    return result


def normalize_ingredients_list(ingredients_list: List[str]) -> List[Dict[str, Any]]:
    """Normalize each string in SupplementLabel.ingredients_list."""
    return [normalize_line(line) for line in ingredients_list if line and line.strip()]


def normalize_scraped_label(scraped: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input: dict like SupplementLabel.model_dump() with keys
    brand, product_name, ingredients_list, serving_size, citations_found.
    Output: same keys + 'ingredients_normalized' list.
    """
    ingredients = scraped.get("ingredients_list") or []
    return {
        "brand": scraped.get("brand"),
        "product_name": scraped.get("product_name"),
        "serving_size": scraped.get("serving_size"),
        "citations_found": scraped.get("citations_found", []),
        "ingredients_normalized": normalize_ingredients_list(ingredients),
    }


if __name__ == "__main__":
    samples = [
        "Vitamin D (as D3 Cholecalciferol) 125 mcg (5,000 IU)",
        "Vitamin D3 (as cholecalciferol) 125 mcg",
        "Vitamin A (as retinyl palmitate) 900 mcg",
        "Magnesium (as magnesium citrate) 200 mg",
    ]
    for s in samples:
        print(s)
        print("  ->", normalize_line(s))
        print()
