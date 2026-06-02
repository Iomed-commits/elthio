"""
feed_manager.py — Elthio Affiliate Feed Manager

Ingests product feeds from affiliate retailers into Supabase.
Currently supports: iHerb (CSV/TSV feed), Amazon PA-API, manual catalog.
Run daily via cron or Railway scheduled job.

Usage:
    python feed_manager.py --retailer iherb
    python feed_manager.py --retailer amazon --query "magnesium glycinate"
    python feed_manager.py --retailer all
    python feed_manager.py --stats
"""

from __future__ import annotations
import os
import csv
import time
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

import scoring
from scoring import FORM_BIOAVAILABILITY_SCORES, VERIFICATION_BADGES  # re-export

log = logging.getLogger(__name__)

SUPPORTED_RETAILERS = ["iherb", "amazon", "life_extension", "vitacost", "swanson"]

SUPPLEMENT_CATEGORIES = [
    "magnesium", "vitamin d", "vitamin d3", "omega-3", "fish oil",
    "coq10", "ubiquinol", "zinc", "iron", "vitamin c", "vitamin b12",
    "vitamin k2", "calcium", "probiotics", "collagen", "biotin",
    "turmeric", "curcumin", "ashwagandha", "melatonin", "5-htp",
    "l-theanine", "vitamin e", "vitamin a", "selenium", "iodine",
    "berberine", "alpha lipoic acid", "NAC", "glutathione",
]


class ProductRecord:
    """Normalised product record from any retailer."""

    def __init__(self, **kwargs):
        self.retailer:          str = kwargs.get("retailer", "")
        self.retailer_id:       str = kwargs.get("retailer_id", "")
        self.brand:             str = kwargs.get("brand", "")
        self.product_name:      str = kwargs.get("product_name", "")
        self.supplement_type:   str = kwargs.get("supplement_type", "")
        self.form:              str = kwargs.get("form", "")
        self.dose_amount:       float = float(kwargs.get("dose_amount", 0) or 0)
        self.dose_unit:         str = kwargs.get("dose_unit", "mg")
        self.servings:          int = int(kwargs.get("servings", 0) or 0)
        self.price:             float = float(kwargs.get("price", 0) or 0)
        self.image_url:         str = kwargs.get("image_url", "")
        self.product_url:       str = kwargs.get("product_url", "")
        self.affiliate_url:     str = kwargs.get("affiliate_url", "")
        self.in_stock:          bool = bool(kwargs.get("in_stock", True))
        self.verified:          bool = bool(kwargs.get("verified", False))
        self.verification_type: str = kwargs.get("verification_type", "")
        self.last_updated:      str = kwargs.get(
            "last_updated",
            datetime.now(timezone.utc).isoformat()
        )

    @property
    def cost_per_serving(self) -> float:
        return scoring.cost_per_serving(self.price, self.servings)

    @property
    def cost_per_active_unit(self) -> float:
        """Cost per mg/mcg/IU of active ingredient — the real value metric."""
        return scoring.cost_per_active_unit(self.cost_per_serving, self.dose_amount)

    @property
    def form_score(self) -> int:
        return scoring.form_score(self.form)

    @property
    def dose_adequacy(self) -> str:
        return scoring.classify_dose(self.supplement_type, self.dose_amount, self.dose_unit)

    @property
    def value_score(self) -> int:
        return scoring.base_value_score(
            cps=self.cost_per_serving,
            form=self.form,
            dose_adequacy=self.dose_adequacy,
            verified=self.verified,
            verif_bonus=scoring.verification_bonus(self.verification_type),
            servings=self.servings,
        )

    def to_dict(self) -> dict:
        return {
            "retailer":           self.retailer,
            "retailer_id":        self.retailer_id,
            "brand":              self.brand,
            "product_name":       self.product_name,
            "supplement_type":    self.supplement_type,
            "form":               self.form,
            "dose_amount":        self.dose_amount,
            "dose_unit":          self.dose_unit,
            "servings":           self.servings,
            "price":              self.price,
            "cost_per_serving":   self.cost_per_serving,
            "cost_per_active_unit": self.cost_per_active_unit,
            "form_score":         self.form_score,
            "dose_adequacy":      self.dose_adequacy,
            "value_score":        self.value_score,
            "image_url":          self.image_url,
            "product_url":        self.product_url,
            "affiliate_url":      self.affiliate_url,
            "in_stock":           self.in_stock,
            "verified":           self.verified,
            "verification_type":  self.verification_type,
            "last_updated":       self.last_updated,
        }


class IHerbFeedIngester:
    """
    Ingests iHerb affiliate product datafeed (CSV/TSV format).
    Request feed access at: iherb.com/info/affiliate-program
    Feed format: tab-separated with columns including SKU, name, price, URL, image.
    """

    AFFILIATE_CODE = os.environ.get("IHERB_AFFILIATE_CODE", "")

    def parse_feed_row(self, row: dict) -> "ProductRecord | None":
        try:
            name = row.get("product_name") or row.get("name") or ""
            brand = row.get("brand") or row.get("manufacturer") or ""
            price = float(row.get("price") or row.get("retail_price") or 0)
            url = row.get("product_url") or row.get("url") or ""
            image = row.get("image_url") or row.get("image") or ""
            sku = row.get("sku") or row.get("id") or ""

            if not name or price <= 0:
                return None

            affiliate_url = url
            if self.AFFILIATE_CODE and url:
                sep = "&" if "?" in url else "?"
                affiliate_url = f"{url}{sep}rcode={self.AFFILIATE_CODE}"

            supp_type = self._detect_supplement_type(name)

            return ProductRecord(
                retailer="iherb",
                retailer_id=str(sku),
                brand=brand,
                product_name=name,
                supplement_type=supp_type or "",
                price=price,
                image_url=image,
                product_url=url,
                affiliate_url=affiliate_url,
                in_stock=True,
            )
        except Exception as e:
            log.warning("iHerb feed parse error: %s", e)
            return None

    def ingest_csv(self, filepath: str) -> "list[ProductRecord]":
        records = []
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                record = self.parse_feed_row(row)
                if record:
                    records.append(record)
        log.info("iHerb feed: parsed %d records from %s", len(records), filepath)
        return records

    def _detect_supplement_type(self, name: str) -> "str | None":
        from basket_compare import detect_supplement_type
        return detect_supplement_type(name)


class AmazonFeedIngester:
    """
    Amazon Product Advertising API v5 ingester.
    Requires: AWS access key, secret key, associate tag.
    Apply at: webservices.amazon.com/paapi5
    Needs a live website before approval.
    """

    ACCESS_KEY    = os.environ.get("AMAZON_PA_ACCESS_KEY", "")
    SECRET_KEY    = os.environ.get("AMAZON_PA_SECRET_KEY", "")
    ASSOCIATE_TAG = os.environ.get("AMAZON_ASSOCIATE_TAG", "")
    REGION        = "us-east-1"
    HOST          = "webservices.amazon.com"

    def is_configured(self) -> bool:
        return all([self.ACCESS_KEY, self.SECRET_KEY, self.ASSOCIATE_TAG])

    def search_supplements(
        self,
        keywords: str,
        max_results: int = 10,
    ) -> "list[ProductRecord]":
        if not self.is_configured():
            log.warning("Amazon PA-API not configured — set AMAZON_PA_ACCESS_KEY, "
                        "AMAZON_PA_SECRET_KEY, AMAZON_ASSOCIATE_TAG in .env")
            return []
        try:
            import paapi5_python_sdk as amazon
            config = amazon.Configuration()
            config.access_key = self.ACCESS_KEY
            config.secret_key = self.SECRET_KEY
            config.host = self.HOST
            config.region = self.REGION

            client = amazon.DefaultApi(amazon.ApiClient(config))
            request = amazon.SearchItemsRequest(
                partner_tag=self.ASSOCIATE_TAG,
                partner_type=amazon.PartnerType.ASSOCIATES,
                keywords=keywords,
                search_index="HealthPersonalCare",
                item_count=max_results,
                resources=[
                    "ItemInfo.Title",
                    "ItemInfo.ByLineInfo",
                    "Offers.Listings.Price",
                    "Images.Primary.Large",
                    "ItemInfo.Features",
                ],
            )
            response = client.search_items(request)
            return self._parse_response(response)
        except ImportError:
            log.warning("paapi5-python-sdk not installed — run: "
                        "pip install paapi5-python-sdk")
            return []
        except Exception as e:
            log.error("Amazon PA-API error: %s", e)
            return []

    def _parse_response(self, response) -> "list[ProductRecord]":
        records = []
        for item in (response.search_result.items or []):
            try:
                name = item.item_info.title.display_value or ""
                brand = ""
                if item.item_info.by_line_info:
                    brand = item.item_info.by_line_info.brand.display_value or ""
                price = 0.0
                if item.offers and item.offers.listings:
                    price = float(
                        item.offers.listings[0].price.amount or 0
                    )
                image = ""
                if item.images and item.images.primary:
                    image = item.images.primary.large.url or ""
                url = f"https://www.amazon.com/dp/{item.asin}"
                affiliate_url = (
                    f"https://www.amazon.com/dp/{item.asin}"
                    f"?tag={self.ASSOCIATE_TAG}"
                )
                from basket_compare import detect_supplement_type
                records.append(ProductRecord(
                    retailer="amazon",
                    retailer_id=item.asin,
                    brand=brand,
                    product_name=name,
                    supplement_type=detect_supplement_type(name) or "",
                    price=price,
                    image_url=image,
                    product_url=url,
                    affiliate_url=affiliate_url,
                    in_stock=True,
                ))
            except Exception as e:
                log.warning("Amazon item parse error: %s", e)
        return records


class SupabaseProductCache:
    """
    Stores and retrieves product records from Supabase.
    Table: elthio_products
    Refreshed daily by feed ingesters.
    """

    TABLE = "elthio_products"

    def __init__(self):
        from supabase_client import SupabaseClient
        self.db = SupabaseClient()

    def upsert_products(self, records: "list[ProductRecord]") -> int:
        saved = 0
        for record in records:
            try:
                self.db.client.table(self.TABLE).upsert(
                    record.to_dict(),
                    on_conflict="retailer,retailer_id",
                ).execute()
                saved += 1
            except Exception as e:
                log.warning("Supabase upsert error: %s", e)
        log.info("Saved %d/%d products to Supabase", saved, len(records))
        return saved

    def search(
        self,
        supplement_type: str,
        retailer: "str | None" = None,
        max_results: int = 10,
        in_stock_only: bool = True,
    ) -> "list[dict]":
        try:
            query = (
                self.db.client.table(self.TABLE)
                .select("*")
                .eq("supplement_type", supplement_type)
            )
            if retailer:
                query = query.eq("retailer", retailer)
            if in_stock_only:
                query = query.eq("in_stock", True)
            query = query.order("value_score", desc=True).limit(max_results)
            result = query.execute()
            return result.data or []
        except Exception as e:
            log.warning("Supabase search error: %s", e)
            return []

    def get_price_history(
        self,
        retailer: str,
        retailer_id: str,
        days: int = 30,
    ) -> "list[dict]":
        try:
            from datetime import timedelta
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).isoformat()
            result = (
                self.db.client.table("elthio_price_history")
                .select("price,recorded_at")
                .eq("retailer", retailer)
                .eq("retailer_id", retailer_id)
                .gte("recorded_at", cutoff)
                .order("recorded_at", desc=False)
                .execute()
            )
            return result.data or []
        except Exception as e:
            log.warning("Price history error: %s", e)
            return []


def seed_from_catalog() -> int:
    """
    Seed the Supabase cache with the curated fallback catalog so the cache-first
    request path can be wired and tested before live affiliate feeds are approved.
    Real feeds later overwrite these rows (same retailer + retailer_id key).
    """
    from shopping_agent import FALLBACK_CATALOG

    code = os.environ.get("IHERB_AFFILIATE_CODE", "")
    records: list[ProductRecord] = []
    for item in FALLBACK_CATALOG:
        url = item.get("source_url", "") or ""
        affiliate = url
        if code and url:
            sep = "&" if "?" in url else "?"
            affiliate = f"{url}{sep}rcode={code}"
        records.append(ProductRecord(
            retailer="iherb",
            retailer_id=item.get("id") or url or item.get("product_name", ""),
            brand=item.get("brand", ""),
            product_name=item.get("product_name") or item.get("product", ""),
            supplement_type=item.get("supplement_type", ""),
            form=item.get("form", ""),
            dose_amount=item.get("dose", 0),
            dose_unit=item.get("unit", "mg"),
            servings=item.get("servings", 0),
            price=item.get("price", 0),
            image_url=item.get("image", ""),
            product_url=url,
            affiliate_url=affiliate,
            in_stock=True,
            verified=bool(item.get("verified")),
            verification_type=item.get("verification_type", ""),
        ))
    cache = SupabaseProductCache()
    saved = cache.upsert_products(records)
    log.info("Seeded %d curated catalog products into Supabase", saved)
    return saved


def run_feed_update(retailer: str = "all") -> "dict[str, int]":
    results = {}

    if retailer in ("iherb", "all"):
        feed_path = os.environ.get("IHERB_FEED_PATH", "")
        if feed_path and Path(feed_path).exists():
            ingester = IHerbFeedIngester()
            records = ingester.ingest_csv(feed_path)
            if records:
                cache = SupabaseProductCache()
                saved = cache.upsert_products(records)
                results["iherb"] = saved
            else:
                results["iherb"] = 0
        else:
            log.info("iHerb feed path not set — set IHERB_FEED_PATH in .env")
            results["iherb"] = 0

    if retailer in ("amazon", "all"):
        ingester = AmazonFeedIngester()
        if ingester.is_configured():
            total = 0
            cache = SupabaseProductCache()
            for category in SUPPLEMENT_CATEGORIES[:10]:
                records = ingester.search_supplements(category, max_results=5)
                if records:
                    saved = cache.upsert_products(records)
                    total += saved
                time.sleep(1)
            results["amazon"] = total
        else:
            log.info("Amazon PA-API not configured")
            results["amazon"] = 0

    return results


def print_stats():
    try:
        cache = SupabaseProductCache()
        result = (
            cache.db.client.table(SupabaseProductCache.TABLE)
            .select("retailer", count="exact")
            .execute()
        )
        print(f"Total products in cache: {result.count}")

        for retailer in SUPPORTED_RETAILERS:
            r = (
                cache.db.client.table(SupabaseProductCache.TABLE)
                .select("retailer", count="exact")
                .eq("retailer", retailer)
                .execute()
            )
            if r.count:
                print(f"  {retailer:20} {r.count} products")
    except Exception as e:
        print(f"Could not fetch stats: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Elthio feed manager")
    parser.add_argument("--retailer", default="all",
                        choices=SUPPORTED_RETAILERS + ["all"],
                        help="Which retailer feed to ingest")
    parser.add_argument("--stats", action="store_true",
                        help="Print product cache stats")
    parser.add_argument("--seed", action="store_true",
                        help="Seed the cache with the curated catalog (pre-feed testing)")
    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.seed:
        saved = seed_from_catalog()
        print(f"Seeded {saved} curated catalog products into Supabase.")
    else:
        results = run_feed_update(args.retailer)
        print("Feed update complete:")
        for retailer, count in results.items():
            print(f"  {retailer}: {count} products saved")
