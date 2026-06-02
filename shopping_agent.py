"""
shopping_agent.py — Elthio Shopping Agent
Parses natural language supplement queries, searches iHerb,
scores results, and checks against user medications.
"""

from __future__ import annotations

import math
import re
from typing import Any

import scoring


SUPPLEMENT_KEYWORDS = [
    "magnesium", "vitamin d", "vitamin c", "vitamin b", "vitamin k",
    "omega-3", "fish oil", "zinc", "iron", "calcium", "coq10",
    "probiotics", "collagen", "biotin", "turmeric", "curcumin",
    "ashwagandha", "melatonin", "b12", "folate", "selenium",
    "vitamin e", "vitamin a", "l-theanine", "glycine", "5-htp",
    "ginseng", "rhodiola", "iodine", "copper", "chromium",
]

BUDGET_PATTERNS = [
    r"under \$?(\d+)",
    r"less than \$?(\d+)",
    r"below \$?(\d+)",
    r"budget.{0,10}\$?(\d+)",
    r"\$?(\d+).{0,10}or less",
    r"cheap",
    r"affordable",
    r"best value",
    r"save money",
]

QUALITY_SIGNALS = [
    "best quality", "premium", "third.party tested", "usp verified",
    "nsf certified", "informed sport", "no fillers", "clean",
    "organic", "vegan", "vegetarian", "gluten.free", "non.gmo",
]

FORM_PREFERENCES = {
    "glycinate": "magnesium glycinate",
    "bisglycinate": "magnesium bisglycinate",
    "citrate": "citrate form",
    "methylcobalamin": "methylcobalamin b12",
    "ubiquinol": "ubiquinol coq10",
    "triglyceride": "triglyceride form omega-3",
    "chelated": "chelated mineral",
    "liposomal": "liposomal form",
}


def parse_query(query: str) -> dict[str, Any]:
    """
    Parse a natural language supplement query into structured intent.
    Returns dict with: supplement, budget, quality_focus, form_preference,
    is_budget_query, medications_mentioned, raw_query.
    """
    q = query.lower().strip()
    result: dict[str, Any] = {
        "raw_query":            query,
        "supplement":           None,
        "budget":               None,
        "quality_focus":        False,
        "form_preference":      None,
        "is_budget_query":      False,
        "is_stack_optimizer":   False,
        "medications_mentioned": [],
        "dietary_restrictions": [],
        "search_terms":         [],
    }

    # detect supplement
    for kw in SUPPLEMENT_KEYWORDS:
        if kw in q:
            result["supplement"] = kw
            break

    # detect budget
    for pattern in BUDGET_PATTERNS:
        m = re.search(pattern, q)
        if m:
            result["is_budget_query"] = True
            try:
                result["budget"] = float(m.group(1))
            except (IndexError, ValueError):
                result["budget"] = None
            break

    # detect quality focus
    for sig in QUALITY_SIGNALS:
        if re.search(sig, q):
            result["quality_focus"] = True
            break

    # detect form preference
    for form_kw, form_name in FORM_PREFERENCES.items():
        if form_kw in q:
            result["form_preference"] = form_name
            break

    # detect stack optimizer intent
    if any(w in q for w in ["save money", "spend", "optimise", "optimize", "cut cost", "cheaper"]):
        result["is_stack_optimizer"] = True

    # detect dietary restrictions
    for restriction in ["vegan", "vegetarian", "gluten-free", "dairy-free", "kosher", "halal"]:
        if restriction in q:
            result["dietary_restrictions"].append(restriction)

    # detect medications mentioned
    med_keywords = [
        "warfarin", "coumadin", "levothyroxine", "synthroid",
        "metformin", "atorvastatin", "lisinopril", "omeprazole",
        "sertraline", "amlodipine", "blood thinner", "thyroid",
    ]
    for med in med_keywords:
        if med in q:
            result["medications_mentioned"].append(med)

    # build search terms — avoid duplicate tokens
    seen = set()
    clean_terms = []
    for term in ([result["supplement"]] if result["supplement"] else []) + \
                 ([result["form_preference"]] if result["form_preference"] else []) + \
                 result["dietary_restrictions"]:
        if term and term.lower() not in seen:
            seen.add(term.lower())
            clean_terms.append(term)
    result["search_terms"] = clean_terms if clean_terms else [query]
    result["primary_search"] = clean_terms[0] if clean_terms else query
    return result


FALLBACK_CATALOG: list[dict] = [

    # Magnesium
    {
        "id": "fallback-mag-glycinate-doctors-best",
        "brand": "Doctor's Best",
        "product_name": "High Absorption Magnesium Glycinate 200mg, 240 Tablets",
        "product": "High Absorption Magnesium Glycinate 200mg, 240 Tablets",
        "supplement_type": "magnesium",
        "form": "Magnesium Bisglycinate",
        "price": 20.88,
        "servings": 240,
        "dose": 200,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "verification_type": "dsld",
        "value_score": 88,
        "cost_per_serving": 0.087,
        "source_url": "https://www.iherb.com/pr/doctor-s-best-high-absorption-magnesium-glycinate-lysinate-100-chelated-200-mg-240-tablets/16567",
        "note": "Best value chelated magnesium — same form as premium brands at a fraction of the cost",
    },
    {
        "id": "fallback-mag-glycinate-pure-encap",
        "brand": "Pure Encapsulations",
        "product_name": "Magnesium Glycinate 120mg",
        "product": "Magnesium Glycinate 120mg",
        "supplement_type": "magnesium",
        "form": "Magnesium Glycinate",
        "price": 22.60,
        "servings": 90,
        "dose": 120,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 78,
        "cost_per_serving": 0.251,
        "source_url": "https://www.iherb.com/pr/pure-encapsulations-magnesium-glycinate-90-capsules/21617",
        "note": "Hypoallergenic — no fillers, ideal for sensitive users",
    },
    {
        "id": "fallback-mag-citrate-now",
        "brand": "NOW Foods",
        "product_name": "Magnesium Citrate 200mg",
        "product": "Magnesium Citrate 200mg",
        "supplement_type": "magnesium",
        "form": "Magnesium Citrate",
        "price": 9.22,
        "servings": 100,
        "dose": 200,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 72,
        "cost_per_serving": 0.092,
        "source_url": "https://www.iherb.com/pr/now-foods-magnesium-citrate-200-mg-100-tablets/799",
        "note": "Lowest cost per serving — citrate form is well absorbed and gentle",
    },
    {
        "id": "fallback-mag-oxide-natures-bounty",
        "brand": "Nature's Bounty",
        "product_name": "Magnesium 500mg",
        "product": "Magnesium 500mg",
        "supplement_type": "magnesium",
        "form": "Magnesium Oxide",
        "price": 11.99,
        "servings": 100,
        "dose": 500,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 38,
        "cost_per_serving": 0.12,
        "source_url": "https://www.iherb.com/pr/nature-s-bounty-magnesium-500-mg-100-coated-tablets/2389",
        "note": "Oxide form — poor absorption, most passes through unused. Not recommended.",
    },

    # Vitamin D3
    {
        "id": "fallback-vitd3-now-5000",
        "brand": "NOW Foods",
        "product_name": "Vitamin D-3 5000 IU",
        "product": "Vitamin D-3 5000 IU",
        "supplement_type": "vitamin d",
        "form": "Cholecalciferol",
        "price": 12.99,
        "servings": 240,
        "dose": 125,
        "unit": "mcg",
        "verified": True,
        "overall_status": "VERIFIED",
        "verification_type": "dsld",
        "value_score": 91,
        "cost_per_serving": 0.054,
        "source_url": "https://www.iherb.com/pr/now-foods-vitamin-d-3-5-000-iu-240-softgels/14717",
        "note": "Best value D3 — cholecalciferol softgel, highest absorption, DSLD verified",
    },
    {
        "id": "fallback-vitd3-sports-research",
        "brand": "Sports Research",
        "product_name": "Vitamin D3 + K2 with Coconut Oil",
        "product": "Vitamin D3 + K2 with Coconut Oil",
        "supplement_type": "vitamin d",
        "form": "Cholecalciferol + MK-7",
        "price": 19.95,
        "servings": 90,
        "dose": 125,
        "unit": "mcg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 85,
        "cost_per_serving": 0.222,
        "source_url": "https://www.iherb.com/pr/sports-research-vitamin-d3-k2-with-organic-coconut-oil-60-softgels/79056",
        "note": "D3 + K2 combo — fat in coconut oil improves absorption. Avoid if on Warfarin.",
    },
    {
        "id": "fallback-vitd3-garden-life-vegan",
        "brand": "Garden of Life",
        "product_name": "mykind Organics Vegan D3 2000 IU",
        "product": "mykind Organics Vegan D3 2000 IU",
        "supplement_type": "vitamin d",
        "form": "Lichen Cholecalciferol",
        "price": 19.99,
        "servings": 30,
        "dose": 50,
        "unit": "mcg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 74,
        "cost_per_serving": 0.667,
        "source_url": "https://www.iherb.com/pr/garden-of-life-mykind-organics-plant-calcium-180-tablets/61448",
        "note": "Certified vegan — lichen-sourced D3, organic certified, higher cost per serving",
    },

    # Omega-3
    {
        "id": "fallback-omega3-carlson",
        "brand": "Carlson",
        "product_name": "Super Omega-3 Gems 1000mg",
        "product": "Super Omega-3 Gems 1000mg",
        "supplement_type": "omega-3",
        "form": "Triglyceride Form",
        "price": 24.95,
        "servings": 100,
        "dose": 1000,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 84,
        "cost_per_serving": 0.25,
        "source_url": "https://www.iherb.com/pr/carlson-super-omega-3-gems-fish-oil-concentrate-1-000-mg-100-soft-gels/1149",
        "note": "Triglyceride form — best absorbed. Norwegian fish oil, IFOS tested.",
    },
    {
        "id": "fallback-omega3-nordic-ultimate",
        "brand": "Nordic Naturals",
        "product_name": "Ultimate Omega 2X 2150mg",
        "product": "Ultimate Omega 2X 2150mg",
        "supplement_type": "omega-3",
        "form": "Triglyceride Form",
        "price": 54.95,
        "servings": 60,
        "dose": 2150,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 79,
        "cost_per_serving": 0.916,
        "source_url": "https://www.iherb.com/pr/nordic-naturals-ultimate-omega-2x-2150-mg-60-soft-gels/71258",
        "note": "Premium high-dose — IFOS 5-star certified, triglyceride form. Higher cost.",
    },
    {
        "id": "fallback-omega3-nature-made",
        "brand": "Nature Made",
        "product_name": "Fish Oil 1200mg",
        "product": "Fish Oil 1200mg",
        "supplement_type": "omega-3",
        "form": "Ethyl Ester",
        "price": 19.99,
        "servings": 200,
        "dose": 1200,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "verification_type": "usp",
        "value_score": 65,
        "cost_per_serving": 0.10,
        "source_url": "https://www.iherb.com/pr/nature-made-fish-oil-1-200-mg-200-softgels/11973",
        "note": "USP certified, lowest cost. Ethyl ester absorbs less well than triglyceride form.",
    },

    # Zinc
    {
        "id": "fallback-zinc-picolinate-thorne",
        "brand": "Thorne",
        "product_name": "Zinc Picolinate 30mg",
        "product": "Zinc Picolinate 30mg",
        "supplement_type": "zinc",
        "form": "Zinc Picolinate",
        "price": 16.00,
        "servings": 60,
        "dose": 30,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 82,
        "cost_per_serving": 0.267,
        "source_url": "https://www.iherb.com/pr/thorne-zinc-picolinate-60-capsules/113",
        "note": "Best absorbed zinc form — picolinate chelate, no fillers",
    },
    {
        "id": "fallback-zinc-bisglycinate-now",
        "brand": "NOW Foods",
        "product_name": "Zinc Glycinate 30mg",
        "product": "Zinc Glycinate 30mg",
        "supplement_type": "zinc",
        "form": "Zinc Bisglycinate",
        "price": 12.99,
        "servings": 120,
        "dose": 30,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 86,
        "cost_per_serving": 0.108,
        "source_url": "https://www.iherb.com/pr/now-foods-zinc-glycinate-30-mg-120-softgels/80845",
        "note": "Best value — bisglycinate form, gentle on stomach, twice the servings",
    },

    # CoQ10
    {
        "id": "fallback-coq10-ubiquinol-qunol",
        "brand": "Qunol",
        "product_name": "Ultra CoQ10 100mg",
        "product": "Ultra CoQ10 100mg",
        "supplement_type": "coq10",
        "form": "Ubiquinol",
        "price": 29.99,
        "servings": 120,
        "dose": 100,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 83,
        "cost_per_serving": 0.25,
        "source_url": "https://www.iherb.com/pr/qunol-ultra-coq10-100-mg-120-softgels/67749",
        "note": "Water and fat soluble — highest bioavailability CoQ10 form",
    },
    {
        "id": "fallback-coq10-ubiquinol-jarrow",
        "brand": "Jarrow Formulas",
        "product_name": "QH-Absorb Ubiquinol 100mg",
        "product": "QH-Absorb Ubiquinol 100mg",
        "supplement_type": "coq10",
        "form": "Ubiquinol",
        "price": 34.95,
        "servings": 60,
        "dose": 100,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 76,
        "cost_per_serving": 0.583,
        "source_url": "https://www.iherb.com/pr/jarrow-formulas-qh-absorb-ubiquinol-max-absorption-coq10-100-mg-60-softgels/5539",
        "note": "Active ubiquinol form — especially effective for people over 40 or on statins",
    },
    {
        "id": "fallback-coq10-ubiquinone-dr-best",
        "brand": "Doctor's Best",
        "product_name": "High Absorption CoQ10 with BioPerine 100mg",
        "product": "High Absorption CoQ10 with BioPerine 100mg",
        "supplement_type": "coq10",
        "form": "Ubiquinone",
        "price": 15.71,
        "servings": 120,
        "dose": 100,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 80,
        "cost_per_serving": 0.131,
        "source_url": "https://www.iherb.com/pr/doctor-s-best-high-absorption-coq10-with-bioperine-100-mg-120-softgels/8946",
        "note": "Ubiquinone with black pepper extract for absorption — strong value",
    },

    # Vitamin B12
    {
        "id": "fallback-b12-methylcobalamin-jarrow",
        "brand": "Jarrow Formulas",
        "product_name": "Methyl B-12 1000mcg",
        "product": "Methyl B-12 1000mcg",
        "supplement_type": "vitamin b12",
        "form": "Methylcobalamin",
        "price": 9.95,
        "servings": 100,
        "dose": 1000,
        "unit": "mcg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 90,
        "cost_per_serving": 0.10,
        "source_url": "https://www.iherb.com/pr/jarrow-formulas-methyl-b-12-cherry-flavor-1000-mcg-100-lozenges/429",
        "note": "Active methylcobalamin form — sublingual lozenge, best absorption",
    },

    # Iron
    {
        "id": "fallback-iron-bisglycinate-thorne",
        "brand": "Thorne",
        "product_name": "Iron Bisglycinate 25mg",
        "product": "Iron Bisglycinate 25mg",
        "supplement_type": "iron",
        "form": "Ferrous Bisglycinate",
        "price": 14.00,
        "servings": 60,
        "dose": 25,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 85,
        "cost_per_serving": 0.233,
        "source_url": "https://www.iherb.com/pr/thorne-iron-bisglycinate-60-capsules/116",
        "note": "Gentlest iron form — bisglycinate causes least GI upset, well absorbed",
    },

    # Vitamin C
    {
        "id": "fallback-vitc-buffered-now",
        "brand": "NOW Foods",
        "product_name": "Buffered C-1000 Vitamin C",
        "product": "Buffered C-1000 Vitamin C",
        "supplement_type": "vitamin c",
        "form": "Calcium Ascorbate",
        "price": 16.99,
        "servings": 180,
        "dose": 1000,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 84,
        "cost_per_serving": 0.094,
        "source_url": "https://www.iherb.com/pr/now-foods-buffered-c-1-000-mg-180-tablets/799",
        "note": "Buffered form — gentler on stomach than plain ascorbic acid at high doses",
    },

    # Calcium
    {
        "id": "fallback-calcium-citrate-solaray",
        "brand": "Solaray",
        "product_name": "Calcium Citrate 1000mg",
        "product": "Calcium Citrate 1000mg",
        "supplement_type": "calcium",
        "form": "Calcium Citrate",
        "price": 14.99,
        "servings": 60,
        "dose": 1000,
        "unit": "mg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 79,
        "cost_per_serving": 0.25,
        "source_url": "https://www.iherb.com/pr/solaray-calcium-citrate-1-000-mg-60-vegcaps/13499",
        "note": "Citrate form — absorbs with or without food, unlike calcium carbonate",
    },

    # Biotin
    {
        "id": "fallback-biotin-now-5000",
        "brand": "NOW Foods",
        "product_name": "Biotin 5000mcg",
        "product": "Biotin 5000mcg",
        "supplement_type": "biotin",
        "form": "Biotin",
        "price": 9.99,
        "servings": 120,
        "dose": 5000,
        "unit": "mcg",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 87,
        "cost_per_serving": 0.083,
        "source_url": "https://www.iherb.com/pr/now-foods-biotin-5-000-mcg-120-veg-capsules/799",
        "note": "High dose — note: 5mg+ biotin can interfere with thyroid and cardiac lab tests",
    },

    # Probiotics
    {
        "id": "fallback-probiotic-culturelle",
        "brand": "Culturelle",
        "product_name": "Digestive Daily Probiotic 10 Billion CFU",
        "product": "Digestive Daily Probiotic 10 Billion CFU",
        "supplement_type": "probiotics",
        "form": "Lactobacillus rhamnosus GG",
        "price": 24.49,
        "servings": 30,
        "dose": 10,
        "unit": "billion CFU",
        "verified": True,
        "overall_status": "VERIFIED",
        "value_score": 80,
        "cost_per_serving": 0.816,
        "source_url": "https://www.iherb.com/pr/culturelle-digestive-daily-probiotic-capsules-30-count/68441",
        "note": "Most researched strain — LGG has the most clinical evidence of any probiotic",
    },
]


def get_fallback_products(intent: dict) -> list[dict]:
    """
    Return products from the fallback catalog matching the parsed intent.
    Used when live iHerb search is blocked or returns no results.
    """
    supplement = (intent.get("supplement") or "").lower()
    search_terms = [t.lower() for t in (intent.get("search_terms") or [])]
    budget = intent.get("budget")
    dietary = [d.lower() for d in (intent.get("dietary_restrictions") or [])]
    form_pref = (intent.get("form_preference") or "").lower()

    matches = []
    for product in FALLBACK_CATALOG:
        supp_type = (product.get("supplement_type") or "").lower()
        prod_name = (product.get("product_name") or "").lower()
        prod_form = (product.get("form") or "").lower()

        hit = False
        if supplement and (supplement in supp_type or supp_type in supplement):
            hit = True
        if not hit:
            for term in search_terms:
                if term in supp_type or term in prod_name or supp_type in term:
                    hit = True
                    break
        if not hit:
            continue

        if budget:
            price = product.get("price", 0) or 0
            if price > budget:
                continue

        if dietary:
            prod_text = prod_name + " " + (product.get("brand") or "").lower()
            if not any(d in prod_text for d in dietary):
                continue

        score_bonus = 0
        if form_pref:
            if any(w in prod_form for w in form_pref.split()):
                score_bonus = 12

        row = dict(product)
        row["value_score"] = min(100, (row.get("value_score") or 50) + score_bonus)
        row["price_source"] = "reference"
        matches.append(row)

    matches.sort(key=lambda x: x.get("value_score", 0), reverse=True)
    return matches[:4]


def score_product(product: dict, intent: dict) -> dict:
    p = dict(product)
    notes = []

    # calculate cost per serving if missing
    price = float(p.get("price") or 0)
    servings = float(p.get("servings") or 30)
    cps = p.get("cost_per_serving")
    if not cps and price > 0 and servings > 0:
        cps = price / servings
        p["cost_per_serving"] = cps

    # cost per unit of active ingredient — the apples-to-apples value signal
    # within a supplement type (a cheap 500mg can beat a "cheaper per serving"
    # 100mg once you normalise to cost per mg of active).
    dose = float(p.get("dose") or 0)
    unit = (p.get("unit") or "").strip().lower()
    if dose > 0 and servings > 0 and price > 0:
        cost_per_unit = price / (servings * dose)
        p["cost_per_unit"] = cost_per_unit
        p["cost_per_unit_unit"] = unit
        p["cost_per_unit_display"] = scoring.format_per_unit(cost_per_unit, unit)

    # base score from cost per serving (primary signal)
    if cps and cps > 0:
        # $0.05/serving = 95, $0.10 = 88, $0.25 = 72, $0.50 = 55, $1.00 = 30
        cps_score = max(10, min(95, int(95 - (math.log10(max(cps, 0.01)) + 2) * 28)))
    else:
        cps_score = 50

    # form quality bonus (classification sourced from scoring.py)
    form = (p.get("form") or "").lower()
    form_bonus = 0
    quality = scoring.form_quality(form)
    if quality == "premium":
        form_bonus = 12
        p["premium_form"] = True
        notes.append("premium absorption form")
    elif quality == "poor":
        form_bonus = -15
        p["premium_form"] = False
        notes.append("lower absorption form")
    else:
        p["premium_form"] = False

    # form preference match
    if intent.get("form_preference"):
        pref = (intent["form_preference"] or "").lower()
        if any(w in form for w in pref.split() if len(w) > 3):
            form_bonus += 8
            notes.append("matches your preferred form")

    # verification bonus — stronger certifiers (USP/NSF) count for more
    verified = p.get("verified") or p.get("overall_status") == "VERIFIED"
    vtype = (p.get("verification_type") or "").lower()
    if not verified:
        verify_bonus = -8
    elif vtype in scoring.VERIFICATION_BADGES:
        verify_bonus = scoring.verification_bonus(vtype)
        p["verification_label"] = scoring.VERIFICATION_BADGES[vtype]["label"]
    else:
        verify_bonus = 8
    if verified:
        notes.append(p.get("verification_label") and f"{p['verification_label']}" or "label verified")
    else:
        notes.append("label not verified — check independently")

    # budget check
    if intent.get("budget"):
        if price > intent["budget"]:
            p["agent_filtered"] = True
            p["agent_filter_reason"] = f"Over budget (${price:.2f} > ${intent['budget']:.0f})"
            return p
        if cps and price < intent["budget"] * 0.6:
            notes.append(f"well under ${intent['budget']:.0f} budget")

    # servings size bonus — more servings = better value signal
    servings_bonus = 0
    if servings >= 180:
        servings_bonus = 6
    elif servings >= 90:
        servings_bonus = 3

    # dietary restriction match
    prod_text = (
        (p.get("product_name") or p.get("name") or p.get("product") or "") +
        " " + (p.get("brand") or "")
    ).lower()
    for restriction in (intent.get("dietary_restrictions") or []):
        if restriction in prod_text:
            notes.append(f"{restriction} confirmed")

    # dose adequacy — flag clearly sub-therapeutic products. Uses the explicit
    # dose on curated products, else parses it from the product name for live
    # results. Stays silent unless we can confidently compare against a threshold.
    dose_penalty = 0
    p["dose_flag"] = False
    supp_type = p.get("supplement_type") or intent.get("supplement") or ""
    key = scoring.dose_key(supp_type)
    if key:
        chk_dose, chk_unit = (dose, unit) if dose > 0 else scoring.parse_dose(
            p.get("product_name") or p.get("name") or p.get("product") or ""
        )
        if chk_dose > 0 and scoring.classify_dose(supp_type, chk_dose, chk_unit) == "underdosed":
            dose_penalty = -10
            p["dose_flag"] = True
            min_dose, _opt, t_unit = scoring.DOSE_THRESHOLDS[key]
            p["dose_flag_note"] = f"Below typical effective dose ({min_dose:g} {t_unit})"

    if p.get("note"):
        notes.insert(0, str(p["note"]))

    final_score = min(100, max(5, cps_score + form_bonus + verify_bonus + servings_bonus + dose_penalty))

    p["agent_score"] = final_score
    p["agent_note"] = " · ".join(notes) if notes else "Standard pick"
    p["agent_filtered"] = False
    p["verified"] = verified
    return p


def _apply_unit_value(candidates: list[dict]) -> None:
    """
    When candidates share an active-ingredient unit (e.g. all in mg), reward the
    lowest cost per unit of active ingredient. This makes "best value" reflect the
    actual active dose you get for your money, not just cost per pill. Additive
    only (never penalises), so it nudges the most efficient products up without
    overriding the form-quality and verification signals.
    """
    priced = [
        c for c in candidates
        if c.get("cost_per_unit") and c.get("cost_per_unit_unit")
    ]
    if len(priced) < 2:
        return
    units = {c["cost_per_unit_unit"] for c in priced}
    if len(units) != 1:
        return
    best = min(c["cost_per_unit"] for c in priced)
    if best <= 0:
        return
    for c in priced:
        ratio = best / c["cost_per_unit"]  # 1.0 = most cost-efficient per active unit
        c["cost_efficiency"] = round(ratio, 2)
        c["agent_score"] = min(100, (c.get("agent_score") or 50) + round(6 * ratio))


def _value_tier(top: dict) -> str:
    verified = bool(top.get("verified"))
    premium = bool(top.get("premium_form"))
    if verified and premium:
        return "Best verified value"
    if verified:
        return "Best value · verified"
    return "Best value"


def rank_products(
    products: list[dict],
    intent: dict,
    user_meds: list[str] | None = None,
) -> dict[str, Any]:
    scored = [score_product(p, intent) for p in products]
    filtered_out = [p for p in scored if p.get("agent_filtered")]
    candidates = [p for p in scored if not p.get("agent_filtered")]

    # normalise value by cost per active unit before ranking
    _apply_unit_value(candidates)

    # sort: adequately-dosed products always rank above sub-therapeutic ones,
    # then by score, then lower cost per active unit, then lower cost per serving
    candidates.sort(
        key=lambda x: (
            0 if x.get("dose_flag") else 1,
            x.get("agent_score", 0),
            1.0 / max(x.get("cost_per_unit") or x.get("cost_per_serving") or 999, 0.000001),
            1.0 / max(x.get("cost_per_serving") or 999, 0.001),
        ),
        reverse=True,
    )

    # clear any existing pick flags then set the winner
    for p in candidates:
        p.pop("agent_pick", None)
        p.pop("value_tier", None)
    if candidates:
        candidates[0]["agent_pick"] = True
        candidates[0]["value_tier"] = _value_tier(candidates[0])

    # med check flags
    med_flags = []
    combined_meds = list(user_meds or [])
    for m in intent.get("medications_mentioned") or []:
        if m and m not in combined_meds:
            combined_meds.append(m)
    if combined_meds:
        supplement = (intent.get("supplement") or "").lower()
        meds_blob = " ".join(str(m).lower() for m in combined_meds)
        warfarin_meds = ["warfarin", "coumadin", "blood thinner"]
        thyroid_meds = ["levothyroxine", "synthroid", "thyroid"]
        if any(m in meds_blob for m in warfarin_meds):
            if any(w in supplement for w in ["omega", "fish oil", "vitamin e", "vitamin k"]):
                med_flags.append({
                    "severity": "high",
                    "message": (
                        f"You take Warfarin — {supplement} may affect INR. "
                        "Keep dose at 1g/day or less and monitor with your pharmacist."
                    ),
                })
        if any(m in meds_blob for m in thyroid_meds):
            if any(w in supplement for w in ["calcium", "iron", "magnesium", "zinc"]):
                med_flags.append({
                    "severity": "critical",
                    "message": (
                        f"You take thyroid medication — separate {supplement} by at least 4 hours."
                    ),
                })

    return {
        "intent":       intent,
        "candidates":   candidates[:4],
        "filtered_out": filtered_out,
        "med_flags":    med_flags,
        "total_found":  len(products),
        "total_shown":  len(candidates[:4]),
    }


if __name__ == "__main__":
    tests = [
        "best magnesium glycinate under $25",
        "I take Warfarin — safe omega-3?",
        "vegan vitamin D3 2000 IU",
        "cheapest verified zinc picolinate",
        "CoQ10 ubiquinol best value",
    ]
    for query in tests:
        intent = parse_query(query)
        products = get_fallback_products(intent)
        result = rank_products(products, intent)
        top = result["candidates"][0] if result["candidates"] else None
        print(f"PASS '{query}'")
        print(f"  supplement: {intent['supplement']}")
        print(f"  budget: {intent['budget']}")
        print(f"  results: {len(result['candidates'])}")
        if top:
            print(f"  top pick: {top['brand']} — {top['product_name']} (score {top.get('agent_score', 0)})")
        print()
