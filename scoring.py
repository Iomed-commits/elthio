"""
scoring.py — Elthio shared product scoring

Single source of truth for the *facts* used to score supplement value:
  - form bioavailability (which forms absorb well)
  - dose adequacy thresholds (what counts as a real effective dose)
  - third-party verification badges
  - cost-per-serving / cost-per-active-unit math
  - a recalibrated base value score

Both the request-time scorer (shopping_agent.score_product) and the
ingestion-time scorer (feed_manager.ProductRecord.value_score) import from here
so they can never drift apart.
"""

from __future__ import annotations

import math
import re


# ---------------------------------------------------------------------------
# Form bioavailability — higher = better absorbed. 50 is the neutral default
# used when a form is unknown.
# ---------------------------------------------------------------------------
FORM_BIOAVAILABILITY_SCORES: dict[str, int] = {
    "glycinate":         95,
    "bisglycinate":      95,
    "malate":            90,
    "citrate":           85,
    "picolinate":        85,
    "chelate":           85,
    "albion":            85,
    "traacs":            85,
    "methylcobalamin":   95,
    "adenosylcobalamin": 90,
    "ubiquinol":         90,
    "triglyceride":      88,
    "phospholipid":      88,
    "liposomal":         87,
    "methylfolate":      92,
    "5-mthf":            92,
    "gluconate":         75,
    "orotate":           75,
    "cyanocobalamin":    70,
    "folic acid":        70,
    "ubiquinone":        60,
    "ethyl ester":       55,
    "sulfate":           50,
    "carbonate":         40,
    "oxide":             35,
}

PREMIUM_FORM_THRESHOLD = 85   # >= is "premium absorption"
POOR_FORM_THRESHOLD = 55      # <= (and a known match) is "lower absorption"


def form_score(form: str) -> int:
    """Bioavailability score 0-100 for a form string (50 if unknown)."""
    f = (form or "").lower()
    for key, score in FORM_BIOAVAILABILITY_SCORES.items():
        if key in f:
            return score
    return 50


def form_quality(form: str) -> str:
    """Classify a form as 'premium', 'poor', or 'standard'."""
    f = (form or "").lower()
    matched = None
    for key, score in FORM_BIOAVAILABILITY_SCORES.items():
        if key in f:
            matched = score
            break
    if matched is None:
        return "standard"
    if matched >= PREMIUM_FORM_THRESHOLD:
        return "premium"
    if matched <= POOR_FORM_THRESHOLD:
        return "poor"
    return "standard"


# ---------------------------------------------------------------------------
# Third-party verification badges
# ---------------------------------------------------------------------------
VERIFICATION_BADGES = {
    "usp":            {"label": "USP Verified",      "score_bonus": 15},
    "nsf":            {"label": "NSF Certified",     "score_bonus": 15},
    "informed_sport": {"label": "Informed Sport",    "score_bonus": 12},
    "consumerlab":    {"label": "ConsumerLab",       "score_bonus": 12},
    "dsld":           {"label": "NIH DSLD Verified", "score_bonus": 10},
    "cgmp":           {"label": "cGMP Certified",    "score_bonus": 6},
    "third_party":    {"label": "3rd Party Tested",  "score_bonus": 8},
}

DEFAULT_VERIFICATION_BONUS = 8


def verification_bonus(verification_type: str) -> int:
    return VERIFICATION_BADGES.get(
        verification_type or "", {}
    ).get("score_bonus", DEFAULT_VERIFICATION_BONUS)


# ---------------------------------------------------------------------------
# Dose adequacy. Thresholds are a conservative (min, optimal) pair in the noted
# canonical unit. `min` is set deliberately low so we only flag clearly
# sub-therapeutic products; `optimal` marks a solid daily dose.
# ---------------------------------------------------------------------------
DOSE_THRESHOLDS: dict[str, tuple[float, float, str]] = {
    "magnesium":   (100, 200, "mg"),
    "vitamin d":   (25, 50, "mcg"),    # 1000 IU / 2000 IU
    "vitamin c":   (250, 500, "mg"),
    "zinc":        (5, 30, "mg"),
    "iron":        (8, 18, "mg"),
    "calcium":     (200, 500, "mg"),
    "coq10":       (30, 100, "mg"),
    "vitamin b12": (100, 500, "mcg"),
    "selenium":    (55, 100, "mcg"),
    "omega-3":     (300, 1000, "mg"),
    "vitamin k2":  (45, 100, "mcg"),
    "melatonin":   (0.3, 1.0, "mg"),
}

_DOSE_RE = re.compile(r"(\d[\d,]*\.?\d*)\s*(mcg|µg|ug|mg|g|iu)\b", re.IGNORECASE)


def parse_dose(text: str) -> tuple[float, str]:
    """Extract the front-of-label active dose + unit from a product name."""
    if not text:
        return (0.0, "")
    m = _DOSE_RE.search(text)
    if not m:
        return (0.0, "")
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return (0.0, "")
    unit = m.group(2).lower()
    if unit in ("µg", "ug"):
        unit = "mcg"
    return (num, unit)


def dose_key(supp_type: str) -> str | None:
    """Map a supplement type/name to a DOSE_THRESHOLDS key."""
    t = (supp_type or "").lower()
    if not t:
        return None
    if "b12" in t:
        return "vitamin b12"
    if "vitamin d" in t or "cholecalciferol" in t:
        return "vitamin d"
    if "vitamin c" in t or "ascorb" in t:
        return "vitamin c"
    if "vitamin k" in t or "menaquinone" in t or "mk-7" in t or "mk7" in t:
        return "vitamin k2"
    if "omega" in t or "fish oil" in t or "epa" in t or "dha" in t:
        return "omega-3"
    if "coq10" in t or "ubiqu" in t:
        return "coq10"
    if "melatonin" in t:
        return "melatonin"
    for k in ("magnesium", "zinc", "iron", "calcium", "selenium"):
        if k in t:
            return k
    return None


def normalise_dose(dose: float, unit: str, target_unit: str, key: str) -> float | None:
    """Convert a parsed dose into the threshold's unit, or None if incomparable."""
    unit = (unit or "").lower()
    if not unit or unit == target_unit:
        # if no unit was parsed, assume it's already in the threshold unit
        return dose
    if unit == "g" and target_unit == "mg":
        return dose * 1000
    if unit == "mg" and target_unit == "mcg":
        return dose * 1000
    if unit == "mcg" and target_unit == "mg":
        return dose / 1000
    if unit == "iu" and target_unit == "mcg" and key == "vitamin d":
        return dose * 0.025  # IU -> mcg for cholecalciferol
    return None


def classify_dose(supp_type: str, dose: float, unit: str = "") -> str:
    """Return 'optimal' | 'adequate' | 'underdosed' | 'unknown'."""
    key = dose_key(supp_type)
    if not key or not dose or dose <= 0:
        return "unknown"
    min_dose, opt_dose, t_unit = DOSE_THRESHOLDS[key]
    norm = normalise_dose(dose, unit, t_unit, key)
    if norm is None:
        return "unknown"
    if norm >= opt_dose:
        return "optimal"
    if norm >= min_dose:
        return "adequate"
    return "underdosed"


# ---------------------------------------------------------------------------
# Cost math
# ---------------------------------------------------------------------------
def cost_per_serving(price: float, servings: float) -> float:
    if servings and price:
        return round(price / servings, 4)
    return 0.0


def cost_per_active_unit(cps: float, dose: float) -> float:
    """Cost per mg/mcg/IU of active ingredient."""
    if not dose or not cps:
        return 0.0
    return round(cps / dose, 6)


def format_per_unit(cost_per_unit: float, unit: str) -> str:
    """Readable cost-per-active-ingredient string, scaled for tiny values."""
    if not cost_per_unit or cost_per_unit <= 0:
        return ""
    u = unit or "unit"
    if cost_per_unit < 0.01:
        return f"${cost_per_unit * 1000:.2f} per 1000 {u}"
    return f"${cost_per_unit:.3f} per {u}"


# ---------------------------------------------------------------------------
# Unified base value score (0-100). Used directly by the feed ingester and as
# the cost backbone for the request-time scorer.
# ---------------------------------------------------------------------------
def base_value_score(
    cps: float,
    form: str,
    dose_adequacy: str,
    verified: bool,
    verif_bonus: int = DEFAULT_VERIFICATION_BONUS,
    servings: int = 0,
) -> int:
    score = 50

    if cps and cps > 0:
        cps_score = max(10, min(90, int(
            90 - (math.log10(max(cps, 0.005)) + 2.3) * 25
        )))
        score = cps_score

    # form contribution is dampened so a premium form alone doesn't saturate the
    # score (premium ~ +18, lower-absorption ~ -6) — keeps good products spread out
    score += round((form_score(form) - 50) * 0.4)

    if dose_adequacy == "optimal":
        score += 8
    elif dose_adequacy == "adequate":
        score += 3
    elif dose_adequacy == "underdosed":
        score -= 15

    if verified:
        score += verif_bonus

    if servings >= 180:
        score += 5
    elif servings >= 90:
        score += 2

    return min(100, max(5, score))
