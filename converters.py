# converters.py

from __future__ import annotations


def normalize_nutrient(value: float, unit: str, nutrient_name: str) -> dict:
    """
    Normalize nutrient values into a canonical form for Bio-Logic verification.

    - Vitamin D: mcg <-> IU   (1 mcg = 40 IU)
    - Vitamin A: mcg <-> IU   (1 mcg RAE ≈ 3.33 IU)
    - All others: returned as-is with unit.
    """
    nutrient = nutrient_name.lower()
    unit = unit.lower()

    # Vitamin D (D2 or D3)
    if "vitamin d" in nutrient:
        if unit in ["mcg", "µg"]:
            return {"mcg": value, "iu": value * 40}
        if unit == "iu":
            return {"mcg": value / 40, "iu": value}

    # Vitamin A (Retinol Activity Equivalents)
    if "vitamin a" in nutrient:
        if unit in ["mcg", "µg"]:
            return {"mcg": value, "iu": round(value * 3.33, 2)}
        if unit == "iu":
            return {"mcg": round(value / 3.33, 2), "iu": value}

    return {"value": value, "unit": unit, "status": "no_conversion_needed"}


if __name__ == "__main__":
    # Simple test with your NOW Foods example: 125 mcg Vitamin D-3
    result = normalize_nutrient(125, "mcg", "Vitamin D-3")
    print("Bio-Logic Normalization:", result)
    # Expected: {'mcg': 125, 'iu': 5000.0}