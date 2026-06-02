from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SiteProfile:
    name: str
    css_selector: Optional[str] = None
    wait_for: Optional[str] = None


LIFE_EXTENSION = SiteProfile(
    name="Life Extension",
    css_selector=(
        ".product-details-container, .product-overview, "
        ".pdp-container, main, #main-content"
    ),
    wait_for=".product-details-container, main",
)

IHERB = SiteProfile(
    name="iHerb",
    # Let crawler.py's Supplement Facts panel detection find the relevant
    # content in the full DOM (prevents scoping to a tiny element).
    css_selector=None,
    wait_for="#supplement-facts, .supplement-facts, [data-name='Supplement Facts']",
)


def infer_site_profile(url: str) -> Optional[SiteProfile]:
    """Return a site profile based on the domain, if known."""

    lowered = url.lower()
    if "lifeextension.com" in lowered:
        return LIFE_EXTENSION
    if "iherb.com" in lowered:
        return IHERB
    return None


__all__ = ["SiteProfile", "LIFE_EXTENSION", "IHERB", "infer_site_profile"]

