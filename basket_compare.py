"""
basket_compare.py — Elthio Basket Comparison
Finds the best price for each supplement across multiple retailers
and calculates the cheapest way to buy a full basket.
"""

from __future__ import annotations
from typing import Any
import os
import re

RETAILER_CONFIG: dict[str, dict] = {
    "iherb": {
        "name": "iHerb",
        "free_shipping_threshold": 40.00,
        "shipping_cost": 6.99,
        "affiliate_param": "rcode",
        "base_url": "https://www.iherb.com",
        "color": "blue",
    },
    "life_extension": {
        "name": "Life Extension",
        "free_shipping_threshold": 50.00,
        "shipping_cost": 5.95,
        "affiliate_param": "utm_source",
        "base_url": "https://www.lifeextension.com",
        "color": "amber",
    },
}

AFFILIATE_CODES: dict[str, str] = {
    "iherb":          os.environ.get("IHERB_AFFILIATE_CODE", ""),
    "life_extension": os.environ.get("LIFE_EXTENSION_AFFILIATE_CODE", ""),
}

LIFE_EXTENSION_CATALOG: list[dict] = [
    {
        "supplement_type": "magnesium",
        "brand": "Life Extension",
        "product_name": "Magnesium Caps 500mg",
        "price": 12.00,
        "servings": 100,
        "form": "Magnesium Oxide",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01233/magnesium-caps",
    },
    {
        "supplement_type": "vitamin d",
        "brand": "Life Extension",
        "product_name": "Vitamin D3 5000 IU",
        "price": 10.00,
        "servings": 60,
        "form": "Cholecalciferol",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01713/vitamin-d3",
    },
    {
        "supplement_type": "coq10",
        "brand": "Life Extension",
        "product_name": "Super Ubiquinol CoQ10 100mg",
        "price": 34.50,
        "servings": 60,
        "form": "Ubiquinol",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01426/super-ubiquinol-coq10",
    },
    {
        "supplement_type": "coq10",
        "brand": "Life Extension",
        "product_name": "PQQ + CoQ10 Capsules",
        "price": 28.00,
        "servings": 30,
        "form": "Ubiquinol",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01500",
    },
    {
        "supplement_type": "zinc",
        "brand": "Life Extension",
        "product_name": "Zinc Caps 50mg",
        "price": 8.25,
        "servings": 90,
        "form": "Zinc Citrate",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01678/zinc-caps",
    },
    {
        "supplement_type": "iron",
        "brand": "Life Extension",
        "product_name": "Iron Protein Plus 300mg",
        "price": 12.00,
        "servings": 100,
        "form": "Iron Protein Succinylate",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01568/iron-protein-plus",
    },
    {
        "supplement_type": "vitamin c",
        "brand": "Life Extension",
        "product_name": "Vitamin C 24 Hour Liposomal 1000mg",
        "price": 22.00,
        "servings": 60,
        "form": "Liposomal",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item02334/vitamin-c-24-hour-liposomal",
    },
    {
        "supplement_type": "omega-3",
        "brand": "Life Extension",
        "product_name": "Super Omega-3 EPA/DHA 120 softgels",
        "price": 24.00,
        "servings": 120,
        "form": "Triglyceride Form",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01982/super-omega-3-epa-dha",
    },
    {
        "supplement_type": "vitamin b12",
        "brand": "Life Extension",
        "product_name": "Methylcobalamin 1mg",
        "price": 14.00,
        "servings": 60,
        "form": "Methylcobalamin",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01578/methylcobalamin",
    },
    {
        "supplement_type": "calcium",
        "brand": "Life Extension",
        "product_name": "Calcium Citrate with Vitamin D3",
        "price": 13.50,
        "servings": 60,
        "form": "Calcium Citrate",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01452/calcium-citrate-with-vitamin-d3",
    },
    {
        "supplement_type": "vitamin k",
        "brand": "Life Extension",
        "product_name": "Super K with Advanced K2 Complex",
        "price": 22.50,
        "servings": 90,
        "form": "MK-7 + MK-4",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01546",
    },
    {
        "supplement_type": "probiotics",
        "brand": "Life Extension",
        "product_name": "FLORASSIST Probiotic 30 capsules",
        "price": 22.00,
        "servings": 30,
        "form": "Multi-strain probiotic",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01702",
    },
    {
        "supplement_type": "probiotics",
        "brand": "Life Extension",
        "product_name": "FLORASSIST Probiotic 30 caps",
        "price": 22.00,
        "servings": 30,
        "form": "Multi-strain probiotic",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01702",
    },
    {
        "supplement_type": "biotin",
        "brand": "Life Extension",
        "product_name": "Biotin 600mcg",
        "price": 8.00,
        "servings": 100,
        "form": "Biotin",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01679/biotin",
    },
    {
        "supplement_type": "selenium",
        "brand": "Life Extension",
        "product_name": "Super Selenium Complex 200mcg",
        "price": 12.00,
        "servings": 100,
        "form": "Selenomethionine",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01648/super-selenium-complex",
    },
    {
        "supplement_type": "melatonin",
        "brand": "Life Extension",
        "product_name": "Melatonin 300mcg",
        "price": 8.00,
        "servings": 100,
        "form": "Melatonin",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01548/melatonin",
    },
    {
        "supplement_type": "curcumin",
        "brand": "Life Extension",
        "product_name": "Super Bio-Curcumin 400mg",
        "price": 22.50,
        "servings": 60,
        "form": "BCM-95 Curcumin",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01709",
    },
    {
        "supplement_type": "vitamin e",
        "brand": "Life Extension",
        "product_name": "Gamma E Tocopherol 465mg",
        "price": 18.00,
        "servings": 60,
        "form": "Mixed Tocopherols",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item00954",
    },
    {
        "supplement_type": "ashwagandha",
        "brand": "Life Extension",
        "product_name": "Ashwagandha 600mg",
        "price": 18.00,
        "servings": 60,
        "form": "KSM-66",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item02088",
    },
    {
        "supplement_type": "collagen",
        "brand": "Life Extension",
        "product_name": "Collagen Peptides Powder",
        "price": 28.00,
        "servings": 30,
        "form": "Hydrolyzed Collagen",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item02392",
    },
    {
        "supplement_type": "ginseng",
        "brand": "Life Extension",
        "product_name": "Asian Energy Boost with Panax Ginseng",
        "price": 22.00,
        "servings": 30,
        "form": "Panax Ginseng Extract",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01676",
    },
    {
        "supplement_type": "l-theanine",
        "brand": "Life Extension",
        "product_name": "L-Theanine 100mg",
        "price": 14.00,
        "servings": 60,
        "form": "L-Theanine",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01524",
    },
    {
        "supplement_type": "zinc",
        "brand": "Life Extension",
        "product_name": "Zinc Caps 50mg 90 caps",
        "price": 8.25,
        "servings": 90,
        "form": "Zinc Citrate",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01678",
    },
    {
        "supplement_type": "5-htp",
        "brand": "Life Extension",
        "product_name": "5-HTP 100mg",
        "price": 14.00,
        "servings": 60,
        "form": "5-Hydroxytryptophan",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item01534",
    },
    {
        "supplement_type": "glycine",
        "brand": "Life Extension",
        "product_name": "Glycine 1000mg",
        "price": 10.00,
        "servings": 100,
        "form": "Glycine",
        "verified": True,
        "url": "https://www.lifeextension.com/vitamins-supplements/item02346",
    },
]

SUPPLEMENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "magnesium":  ["magnesium", "mag glycinate", "mag citrate"],
    "vitamin d":  ["vitamin d", "vitamin d3", "vitamin d-3", "cholecalciferol", "vit d"],
    "coq10":      ["coq10", "coenzyme q10", "ubiquinol", "ubiquinone", "coq-10"],
    "zinc":       ["zinc"],
    "iron":       ["iron", "ferrous", "ferric"],
    "vitamin c":  ["vitamin c", "ascorbic acid", "ascorbate"],
    "omega-3":    ["omega", "fish oil", "epa", "dha", "krill"],
    "vitamin b12":["vitamin b12", "b12", "methylcobalamin", "cyanocobalamin", "cobalamin"],
    "calcium":    ["calcium"],
    "vitamin k":  ["vitamin k", "vitamin k2", "k2", "mk-7", "menaquinone"],
    "probiotics": ["probiotic", "lactobacillus", "bifidobacterium"],
    "biotin":     ["biotin", "vitamin b7"],
    "selenium":   ["selenium"],
    "melatonin":  ["melatonin"],
    "l-theanine":  ["l-theanine", "theanine", "suntheanine"],
    "5-htp":       ["5-htp", "5 htp", "hydroxytryptophan"],
    "glycine":     ["glycine"],
    "ashwagandha": ["ashwagandha", "withania", "ksm-66"],
    "curcumin":    ["curcumin", "turmeric", "curcuma"],
    "ginseng":     ["ginseng", "panax", "rhodiola"],
    "collagen":    ["collagen", "collagen peptides"],
    "vitamin e":   ["vitamin e", "tocopherol", "tocotrienol"],
    "vitamin a":  ["vitamin a", "retinol", "beta-carotene"],
}


def detect_supplement_type(query: str) -> str | None:
    """
    Detect supplement type from natural language query.
    Handles: 'D3+K2', 'Mg glycinate 400mg', 'Ubiquinol 200', 'CoQ-10', etc.
    """
    q = query.lower().strip()
    q = q.replace("+", " ").replace("-", " ").replace("_", " ")
    q = re.sub(r"\d+\s*(mg|mcg|iu|g)\b", "", q)
    q = re.sub(r"\s+", " ", q).strip()

    # exact and alias mappings checked first
    aliases = {
        "d3": "vitamin d",
        "vit d": "vitamin d",
        "vitamin d3": "vitamin d",
        "cholecalciferol": "vitamin d",
        "k2": "vitamin k",
        "mk7": "vitamin k",
        "mk 7": "vitamin k",
        "menaquinone": "vitamin k",
        "mg": "magnesium",
        "mag": "magnesium",
        "b12": "vitamin b12",
        "cobalamin": "vitamin b12",
        "methylcobalamin": "vitamin b12",
        "epa": "omega-3",
        "dha": "omega-3",
        "fish oil": "omega-3",
        "coq10": "coq10",
        "coq 10": "coq10",
        "ubiquinol": "coq10",
        "ubiquinone": "coq10",
        "vit c": "vitamin c",
        "ascorbic": "vitamin c",
        "vit e": "vitamin e",
        "tocopherol": "vitamin e",
        "vit a": "vitamin a",
        "retinol": "vitamin a",
        "ferrous": "iron",
        "ferric": "iron",
        "probiotic": "probiotics",
        "lactobacillus": "probiotics",
    }
    for alias, supp_type in aliases.items():
        if alias in q:
            return supp_type

    for supp_type, keywords in SUPPLEMENT_TYPE_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return supp_type

    return None


def build_affiliate_url(url: str, retailer_key: str) -> str:
    """Append affiliate tracking parameter to product URL."""
    if not url:
        return url
    code = AFFILIATE_CODES.get(retailer_key, "")
    if not code or code == "YOURCODE":
        return url
    sep = "&" if "?" in url else "?"
    if retailer_key == "iherb":
        return f"{url}{sep}rcode={code}"
    return url


def get_life_extension_products(supplement_type: str) -> list[dict]:
    return [
        p for p in LIFE_EXTENSION_CATALOG
        if p.get("supplement_type") == supplement_type
    ]


def calculate_retailer_total(
    items: list[dict],
    retailer_key: str,
) -> dict[str, Any]:
    config = RETAILER_CONFIG[retailer_key]
    subtotal = sum(float(item.get("price") or 0) for item in items if item)
    found_count = len([i for i in items if i])
    shipping = 0.0
    if subtotal < config["free_shipping_threshold"]:
        shipping = config["shipping_cost"]
    total = subtotal + shipping
    return {
        "retailer": retailer_key,
        "retailer_name": config["name"],
        "base_url": config["base_url"],
        "subtotal": round(subtotal, 2),
        "shipping": round(shipping, 2),
        "total": round(total, 2),
        "free_shipping": shipping == 0,
        "free_shipping_threshold": config["free_shipping_threshold"],
        "items_found": found_count,
        "items_total": len(items),
        "color": config["color"],
    }


def build_mix_and_match(
    basket_results: dict[str, list[dict | None]],
    supplements: list[str],
) -> dict[str, Any]:
    mix_items = []
    retailer_subtotals: dict[str, float] = {}

    for i, supp in enumerate(supplements):
        options = []
        for retailer_key, items in basket_results.items():
            if i < len(items) and items[i]:
                item = dict(items[i])
                item["retailer"] = retailer_key
                item["retailer_name"] = RETAILER_CONFIG[retailer_key]["name"]
                options.append(item)
        if not options:
            mix_items.append({"supplement": supp, "best": None, "all_options": []})
            continue
        options.sort(key=lambda x: float(x.get("price") or 999))
        best = options[0]
        mix_items.append({"supplement": supp, "best": best, "all_options": options})
        r_key = best["retailer"]
        retailer_subtotals[r_key] = retailer_subtotals.get(r_key, 0) + float(best.get("price") or 0)

    # calculate shipping per retailer based on that retailer's subtotal
    total_with_shipping = 0.0
    retailer_shipping: dict[str, float] = {}
    for r_key, subtotal in retailer_subtotals.items():
        config = RETAILER_CONFIG.get(r_key, {})
        threshold = config.get("free_shipping_threshold", 999)
        ship_cost = config.get("shipping_cost", 0)
        shipping = 0.0 if subtotal >= threshold else ship_cost
        retailer_shipping[r_key] = shipping
        total_with_shipping += subtotal + shipping

    items_total = sum(
        float(item["best"]["price"])
        for item in mix_items
        if item.get("best")
    )

    return {
        "items": mix_items,
        "items_total": round(items_total, 2),
        "total_with_shipping": round(total_with_shipping, 2),
        "retailer_shipping": retailer_shipping,
        "retailers_used": list(retailer_subtotals.keys()),
        "note": (
            f"Requires {len(retailer_subtotals)} separate order(s). "
            "Shipping per retailer included in total above."
        ),
    }


def compare_basket(
    supplements: list[str],
    iherb_results: dict[str, list[dict]],
) -> dict[str, Any]:
    basket_results: dict[str, list[dict | None]] = {}

    iherb_items: list[dict | None] = []
    for supp in supplements:
        products = iherb_results.get(supp, [])
        if products:
            best = sorted(products, key=lambda p: (
                -(p.get("agent_score") or p.get("value_score") or 0)
            ))[0]
            iherb_items.append(best)
        else:
            iherb_items.append(None)
    basket_results["iherb"] = iherb_items

    le_items: list[dict | None] = []
    for supp in supplements:
        supp_type = detect_supplement_type(supp)
        if supp_type:
            le_products = get_life_extension_products(supp_type)
            le_items.append(le_products[0] if le_products else None)
        else:
            le_items.append(None)
    basket_results["life_extension"] = le_items

    retailer_totals = []
    for retailer_key in ["iherb", "life_extension"]:
        items = basket_results[retailer_key]
        totals = calculate_retailer_total(items, retailer_key)
        totals["items"] = []
        for i, supp in enumerate(supplements):
            item = items[i] if i < len(items) else None
            if item and not item.get("url") and item.get("source_url"):
                item = dict(item)
                item["url"] = item.get("source_url")
            if item and item.get("url"):
                item = dict(item)
                item["url"] = build_affiliate_url(item["url"], retailer_key)
            totals["items"].append({
                "supplement": supp,
                "product": item,
                "available": item is not None,
            })
        retailer_totals.append(totals)

    retailer_totals.sort(key=lambda x: x["total"])

    mix = build_mix_and_match(basket_results, supplements)
    winner = retailer_totals[0]
    mix_saving = round(winner["total"] - mix["total_with_shipping"], 2)

    return {
        "supplements": supplements,
        "retailer_totals": retailer_totals,
        "winner": retailer_totals[0]["retailer"],
        "winner_name": retailer_totals[0]["retailer_name"],
        "winner_total": retailer_totals[0]["total"],
        "mix_and_match": mix,
        "mix_saving": mix_saving if mix_saving > 0.50 else 0,
        "disclaimer": (
            "Prices are approximate and may change. "
            "Elthio earns a commission on purchases through our links."
        ),
    }


if __name__ == "__main__":
    # test type detection edge cases
    test_queries = [
        ("D3+K2",            "vitamin d"),
        ("Mg glycinate",     "magnesium"),
        ("Ubiquinol 200mg",  "coq10"),
        ("CoQ-10",           "coq10"),
        ("fish oil 1000mg",  "omega-3"),
        ("methylcobalamin",  "vitamin b12"),
        ("Iron bisglycinate","iron"),
        ("vit c 1000",       "vitamin c"),
    ]
    print("Type detection tests:")
    all_passed = True
    for query, expected in test_queries:
        result = detect_supplement_type(query)
        passed = result == expected
        if not passed:
            all_passed = False
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark} '{query}' -> {result} (expected {expected})")

    # test shipping math
    print("\nShipping math test:")
    mock_results = {
        "iherb": [
            {"brand":"Thorne","product_name":"Iron","price":14.00,"retailer":"iherb","retailer_name":"iHerb"},
            {"brand":"NOW","product_name":"CoQ10","price":22.99,"retailer":"iherb","retailer_name":"iHerb"},
        ],
        "life_extension": [
            {"brand":"LE","product_name":"Iron LE","price":12.00,"retailer":"life_extension","retailer_name":"Life Extension"},
            {"brand":"LE","product_name":"CoQ10 LE","price":34.50,"retailer":"life_extension","retailer_name":"Life Extension"},
        ],
    }
    mix = build_mix_and_match(mock_results, ["Iron", "CoQ10"])
    print(f"  items_total: ${mix['items_total']:.2f}")
    print(f"  total_with_shipping: ${mix['total_with_shipping']:.2f}")
    print(f"  retailers_used: {mix['retailers_used']}")
    assert mix["total_with_shipping"] >= mix["items_total"], "Shipping math wrong"
    print("  PASS Shipping correctly added")

    print("\nAll tests passed" if all_passed else "\nSOME TESTS FAILED")
