"""
server.py — Elthio
================================
Local API server that connects elthio.html to the pipeline.

Run once:
    python server.py

Then open elthio.html in your browser.
Paste any iHerb or LifeExtension URL and click Audit —
the pipeline runs automatically and results appear in the app.

Endpoints:
    GET  /              → serves elthio.html
    POST /audit         → runs pipeline, returns Golden Record JSON
    GET  /records       → lists all saved Golden Records
    GET  /record/<id>   → returns a specific Golden Record
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
import re
from urllib.parse import parse_qs, unquote, urlparse

from supabase_client import normalize_supabase_url

log = logging.getLogger("elthio.server")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

BASE_DIR = Path(__file__).resolve().parent
RECORDS_DIR = BASE_DIR / "results"
RECORDS_DIR.mkdir(exist_ok=True)

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def _request_path(raw: str) -> str:
    """Normalize path: absolute-form URI, query, fragments, duplicate/trailing slashes."""
    if not raw:
        return "/"
    s = raw.strip()
    if "?" in s:
        s = s.split("?", 1)[0]
    if "#" in s:
        s = s.split("#", 1)[0]
    s = s.replace("\\", "/")
    # Absolute-form request-URI (HTTP/1.1): GET http://host:port/medcheck HTTP/1.1
    if "://" in s:
        s = urlparse(s).path or "/"
    else:
        s = urlparse(s).path or s
        if not s.startswith("/"):
            s = "/" + s.lstrip("/")
    parts = [unquote(seg) for seg in s.split("/") if seg]
    return "/" + "/".join(parts) if parts else "/"


def _med_check_file() -> Path | None:
    """Prefer HTML next to this script; also try cwd (someone may run PY from another folder)."""
    for base in (BASE_DIR, Path.cwd().resolve()):
        p = (base / "med_check.html").resolve()
        try:
            if p.exists() and p.is_file():
                return p
        except OSError:
            continue
    return None


def _is_med_check_api(path: str) -> bool:
    p = (path or "").lower().replace("\\", "/").rstrip("/")
    return p in ("/med-check", "/medcheck")


def _is_medcheck_path(path: str) -> bool:
    if not path or path == "/":
        return False
    p = path.lower().replace("\\", "/").rstrip("/")
    if p in ("/medcheck", "/med-check", "/med_check.html", "/medcheck.html"):
        return True
    segs = [x for x in p.split("/") if x]
    if not segs:
        return False
    last = segs[-1].removesuffix(".html")
    return last in ("medcheck", "med-check", "med_check", "medcheck")


def _want_medcheck(raw: str) -> bool:
    """True if GET should serve med_check (handles oddly encoded paths)."""
    if not raw:
        return False
    variants = []
    stripped = raw.strip()
    variants.append(stripped)
    variants.append(unquote(stripped))
    if "?" in stripped:
        q0 = stripped.split("?", 1)[0]
        variants.append(q0)
        variants.append(unquote(q0))
    seen: set[str] = set()
    for v in variants:
        if v in seen:
            continue
        seen.add(v)
        if _is_medcheck_path(_request_path(v)):
            return True
    return False


def _supplement_passport_file() -> Path | None:
    for base in (BASE_DIR, Path.cwd().resolve()):
        p = (base / "supplement_passport.html").resolve()
        try:
            if p.exists() and p.is_file():
                return p
        except OSError:
            continue
    return None


def _is_passport_path(path: str) -> bool:
    if not path or path == "/":
        return False
    p = path.lower().replace("\\", "/").rstrip("/")
    if p in (
        "/passport",
        "/supplement-passport",
        "/supplement_passport",
        "/supplement_passport.html",
    ):
        return True
    segs = [x for x in p.split("/") if x]
    if not segs:
        return False
    last = segs[-1].removesuffix(".html")
    return last in ("passport", "supplement-passport", "supplement_passport")


def _want_passport(raw: str) -> bool:
    if not raw:
        return False
    variants = []
    stripped = raw.strip()
    variants.append(stripped)
    variants.append(unquote(stripped))
    if "?" in stripped:
        q0 = stripped.split("?", 1)[0]
        variants.append(q0)
        variants.append(unquote(q0))
    seen: set[str] = set()
    for v in variants:
        if v in seen:
            continue
        seen.add(v)
        if _is_passport_path(_request_path(v)):
            return True
    return False


def _visit_packet_file() -> Path | None:
    for base in (BASE_DIR, Path.cwd().resolve()):
        p = (base / "visit_packet.html").resolve()
        try:
            if p.exists() and p.is_file():
                return p
        except OSError:
            continue
    return None


def _is_visit_packet_path(path: str) -> bool:
    if not path or path == "/":
        return False
    p = path.lower().replace("\\", "/").rstrip("/")
    if p in ("/visit-packet", "/visit_packet", "/visit_packet.html"):
        return True
    segs = [x for x in p.split("/") if x]
    if not segs:
        return False
    last = segs[-1].removesuffix(".html")
    return last in ("visit-packet", "visit_packet")


def _want_visit_packet(raw: str) -> bool:
    if not raw:
        return False
    variants = []
    stripped = raw.strip()
    variants.append(stripped)
    variants.append(unquote(stripped))
    if "?" in stripped:
        q0 = stripped.split("?", 1)[0]
        variants.append(q0)
        variants.append(unquote(q0))
    seen: set[str] = set()
    for v in variants:
        if v in seen:
            continue
        seen.add(v)
        if _is_visit_packet_path(_request_path(v)):
            return True
    return False


# Railway and other hosts inject PORT; local default stays 8765 (see start.bat).
PORT = int(os.environ.get("PORT", os.environ.get("ELTHIO_PORT", "8765")))
# Use 0.0.0.0 so http://127.0.0.1:PORT and http://localhost:PORT both work reliably.
# Set ELTHIO_BIND=127.0.0.1 in the environment to listen on loopback only.
BIND = os.environ.get("ELTHIO_BIND", "0.0.0.0")

VERIFIED_BRANDS = {
    "now foods", "thorne", "jarrow formulas", "nordic naturals",
    "carlson", "pure encapsulations", "garden of life", "life extension",
    "nature made", "solgar", "doctor's best", "solaray", "country life",
    "bluebonnet", "klaire labs", "designs for health", "integrative therapeutics",
    "california gold nutrition", "qunol", "culturelle", "sports research",
}


def _quick_verify(product: dict) -> dict:
    p = dict(product)
    brand = (p.get("brand") or "").lower().strip()
    if brand in VERIFIED_BRANDS:
        p["verified"] = True
        p["overall_status"] = "VERIFIED"
    return p


def _safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _form_score(form_name: str) -> int:
    if not form_name:
        return 55
    name = re.sub(r"[()]", " ", form_name.lower())
    form_quality = {
        "cholecalciferol": 95,
        "d-3": 95,
        "vitamin d-3": 95,
        "vitamin d3": 95,
        "d3": 95,
        "ergocalciferol": 60,
        "d2": 60,
        "vitamin k2": 90,
        "mk-7": 95,
        "mk7": 95,
        "menaquinone": 92,
        "d3 k2": 90,
        "k2 mk": 92,
        "magnesium glycinate": 92,
        "magnesium bisglycinate": 92,
        "magnesium malate": 85,
        "magnesium citrate": 80,
        "magnesium l-threonate": 88,
        "magnesium oxide": 35,
        "ascorbic acid": 85,
        "sodium ascorbate": 80,
        "calcium ascorbate": 82,
        "liposomal": 95,
        "ester-c": 88,
        "zinc picolinate": 90,
        "zinc bisglycinate": 88,
        "zinc citrate": 82,
        "zinc gluconate": 72,
        "zinc oxide": 38,
        "methylcobalamin": 95,
        "cyanocobalamin": 65,
        "triglyceride form": 90,
        "ethyl ester": 65,
        "phospholipid": 95,
    }
    best: int | None = None
    for key, score in form_quality.items():
        if key in name:
            best = score if best is None else max(best, score)
    return best if best is not None else 55


def _build_ranked_comparison(records: list[dict]) -> list[dict]:
    ranked = []
    for rec in records:
        audit = rec.get("audit") or []
        primary = next(
            (a for a in audit if a.get("retail_amount") is not None and a.get("retail_unit")),
            None,
        )
        if not primary:
            continue

        price = _safe_float(rec.get("price"))
        servings = _safe_float(rec.get("servings")) or 30.0
        dose = _safe_float(primary.get("retail_amount")) or 0.0
        form_parts = [
            (a.get("name") or "")
            for a in audit
            if (a.get("name"))
            and (a.get("retail_amount") is not None or a.get("retail_unit"))
        ]
        form = " | ".join(form_parts) if form_parts else (primary.get("name") or "")
        verified = rec.get("overall_status") == "VERIFIED"
        cpm = (price / (servings * dose)) if price and servings > 0 and dose > 0 else None
        cost_score = 0.0 if cpm is None else max(0.0, min(100.0, 100.0 - (cpm * 50000.0)))
        value_score = round((cost_score * 0.45) + (_form_score(form) * 0.45) + (10.0 if verified else 0.0))

        ranked.append(
            {
                "brand": rec.get("brand") or "Unknown",
                "product": rec.get("product_name") or "Unknown",
                "price": price if price is not None else 0.0,
                "servings": int(servings) if servings else 30,
                "dose": dose,
                "unit": primary.get("retail_unit") or "mg",
                "form": form,
                "verified": verified,
                "overall_status": rec.get("overall_status"),
                "dsld_id": rec.get("dsld_id"),
                "source_url": rec.get("source_url"),
                "value_score": value_score,
                "cost_per_serving": (price / servings) if price is not None and servings > 0 else None,
                "cost_per_mg": cpm,
            }
        )

    ranked.sort(key=lambda x: x["value_score"], reverse=True)
    return ranked


def parseServings(record: dict, url: str) -> int:
    raw = record.get("servings_per_container")
    n = None
    try:
        if raw is not None and raw != "":
            n = int(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        pass
    if n and n > 0:
        return n
    m = re.search(r"(\d{2,4})[-_](?:softgels?|caps?|tabs?|count)", url, re.I)
    if m:
        try:
            n = int(m.group(1))
            if n >= 10:
                return n
        except ValueError:
            pass
    return 30


def _infer_form_from_title(rec: dict) -> str | None:
    title = (
        (rec.get("product_name") or rec.get("name") or rec.get("product") or "")
    ).lower()
    hints = (
        ("magnesium glycinate", ("glycinate", "bisglycinate")),
        ("magnesium citrate", ("citrate",)),
        ("ubiquinol coq10", ("ubiquinol",)),
        ("triglyceride form omega-3", ("triglyceride", "tg form")),
        ("methylcobalamin b12", ("methylcobalamin",)),
        ("zinc picolinate", ("picolinate",)),
    )
    for form_label, keys in hints:
        if any(k in title for k in keys):
            return form_label
    return None


def _enrich_shopping_product(rec: dict) -> dict:
    """Ensure value_score and compare fields exist for shopping agent ranking."""
    out = dict(rec)
    out["price_source"] = "live"
    url = out.get("url") or out.get("source_url") or ""
    if out.get("servings") is None:
        out["servings"] = parseServings(out, url)
    if out.get("name") and not out.get("product_name"):
        out["product_name"] = out["name"]
    if out.get("product_name") and not out.get("product"):
        out["product"] = out["product_name"]
    if not out.get("form"):
        inferred = _infer_form_from_title(out)
        if inferred:
            out["form"] = inferred
    image = out.get("image")
    ranked = _build_ranked_comparison([out])
    if ranked:
        out.update(ranked[0])
        if image:
            out["image"] = image
    else:
        price = _safe_float(out.get("price")) or 0.0
        servings = _safe_float(out.get("servings")) or 30.0
        out.setdefault("form", "Standard")
        out.setdefault("verified", out.get("overall_status") == "VERIFIED")
        out.setdefault("value_score", 50)
        if price and servings > 0:
            out["cost_per_serving"] = price / servings
    return out


def _cache_row_to_product(row: dict) -> dict:
    """Map a Supabase elthio_products row into the shopping-product shape that
    rank_products / score_product expect."""
    out = dict(row)
    if out.get("dose") is None:
        out["dose"] = row.get("dose_amount")
    if not out.get("unit"):
        out["unit"] = row.get("dose_unit")
    url = row.get("affiliate_url") or row.get("product_url") or ""
    out.setdefault("source_url", url)
    out.setdefault("url", url)
    if not out.get("image"):
        out["image"] = row.get("image_url")
    if not out.get("product"):
        out["product"] = row.get("product_name")
    if row.get("verified"):
        out["overall_status"] = "VERIFIED"
    out["price_source"] = "cached"
    out["cache_last_updated"] = row.get("last_updated")
    return out


def _search_product_cache(intent: dict, max_results: int = 8) -> list:
    """Cache-first lookup against the Supabase product cache. Returns [] on any
    miss/error so callers fall through to live search / curated fallback."""
    try:
        from feed_manager import SupabaseProductCache
        from basket_compare import detect_supplement_type
    except Exception:
        return []

    supp_type = (
        intent.get("supplement")
        or detect_supplement_type(intent.get("primary_search") or "")
        or detect_supplement_type(intent.get("raw_query") or "")
        or ""
    )
    if not supp_type:
        return []
    try:
        cache = SupabaseProductCache()
        rows = cache.search(supp_type, max_results=max_results)
        return [_cache_row_to_product(r) for r in rows]
    except Exception as e:
        log.warning("Product cache lookup failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Pipeline runner (async → sync bridge)
# ---------------------------------------------------------------------------

def run_pipeline_sync(url: str, upc: str = None) -> dict:
    """Run the async pipeline in a sync context."""
    from pipeline import run_audit

    async def _run():
        return await run_audit(url, expected_upc=upc or None, max_retries=3)

    loop = asyncio.new_event_loop()
    try:
        record, err = loop.run_until_complete(_run())
    finally:
        loop.close()

    if not record:
        return {"error": err or "Pipeline returned no record. Check URL and UPC."}

    record_dict = record.to_dict()

    # Save to results folder
    slug = url.split("/pr/")[-1].split("/")[0][:50] if "/pr/" in url else url.split("/")[-2][:50]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"golden_record_{slug}_{ts}.json"
    fpath = RECORDS_DIR / fname
    fpath.write_text(json.dumps(record_dict, indent=2), encoding="utf-8")
    log.info("Saved: %s", fpath)

    record_dict["_saved_as"] = fname
    return record_dict


def run_search_sync(query: str, max_results: int = 8) -> list[dict]:
    """Run async product search in a sync context."""
    from search_products import search_all

    async def _run():
        return await search_all(query=query, max_per_retailer=max_results)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


def _bearer_token_from_headers(headers) -> str:
    raw_auth = headers.get("Authorization", "") or ""
    if raw_auth.lower().startswith("bearer "):
        return raw_auth[7:].strip()
    return raw_auth.replace("Bearer ", "").strip()


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class ElthioHandler(BaseHTTPRequestHandler):
    server_version = "ElthioHTTP/1"

    def log_message(self, format, *args):
        log.info("%s %s", self.address_string(), format % args)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Elthio", "1")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Elthio", "1")
        self.end_headers()
        self.wfile.write(body)

    def _send_cors(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_OPTIONS(self):
        self._send_cors()

    def do_GET(self):
        raw = self.path or "/"
        path = _request_path(raw)
        log.info("GET raw=%r normalized=%r", raw, path)

        # Serve elthio.html at root
        if path in ("/", "/index.html"):
            html_path = BASE_DIR / "elthio.html"
            if not html_path.exists():
                html_path = BASE_DIR / "biologer.html"
            if html_path.exists():
                self._send_html(html_path.read_text(encoding="utf-8"))
            else:
                self._send_json({"error": "elthio.html not found in current directory"}, 404)
            return

        # Serve med_check.html (several paths for compat with proxies / old links)
        if _want_medcheck(raw):
            html_path = _med_check_file()
            if html_path:
                log.info("GET %s -> %s", self.path, html_path.name)
                self._send_html(html_path.read_text(encoding="utf-8"))
            else:
                log.error("med_check.html missing; BASE_DIR=%s cwd=%s", BASE_DIR, Path.cwd())
                self._send_json(
                    {
                        "error": "med_check.html not found",
                        "hint": f"Expect {BASE_DIR / 'med_check.html'} beside Server.PY, or run from folder that contains it.",
                    },
                    404,
                )
            return

        if path == "/separation-rules":
            try:
                from rules import RULES

                public = [
                    {k: v for k, v in row.items() if k not in ("med_keywords", "supp_keywords")}
                    for row in RULES
                ]
                self._send_json({"rules": public})
            except Exception as e:
                log.warning("separation-rules: %s", e)
                self._send_json({"error": str(e), "rules": []}, 500)
            return

        if path == "/config":
            self._send_json(
                {
                    "supabase_url": normalize_supabase_url(os.environ.get("SUPABASE_URL", "")),
                    "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
                }
            )
            return

        if path == "/api/health":
            key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            self._send_json(
                {
                    "ok": True,
                    "anthropic_configured": key.startswith("sk-ant"),
                    "claude_model": "claude-sonnet-4-5-20250929",
                }
            )
            return

        if path == "/api/load-stack" or path.startswith("/api/load-stack"):
            try:
                qs    = parse_qs(urlparse(self.path).query)
                email = (qs.get("email") or [""])[0].strip()
                if not email:
                    self._send_json({"error": "email required"}, 400)
                    return
                from stack_save import get_stack
                stack = get_stack(email)
                if stack:
                    self._send_json({"found": True,  "stack": stack})
                else:
                    self._send_json({"found": False, "stack": None})
            except Exception as e:
                log.error("load-stack error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path.startswith("/api/price-search"):
            try:
                qs       = parse_qs(urlparse(self.path).query)
                query    = (qs.get("q", [""])[0] or "").strip()
                retailer = (qs.get("retailer", [None])[0] or None) or None
                form     = (qs.get("form", [None])[0] or None) or None
                sort     = (qs.get("sort", ["cost_per_serving"])[0] or "cost_per_serving")
                try:
                    max_p = float(qs.get("max_price", [None])[0])
                except (TypeError, ValueError):
                    max_p = None
                if not query:
                    self._send_json({"error": "q is required"}, 400)
                    return
                from price_monitor import search_prices
                results = search_prices(query, retailer, form, max_p, sort)
                self._send_json({"results": results, "query": query, "count": len(results)})
            except Exception as e:
                log.error("price-search error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/auth":
            html_path = BASE_DIR / "auth.html"
            if html_path.exists():
                self._send_html(html_path.read_text(encoding="utf-8"))
            else:
                self._send_json({"error": "auth.html not found"}, 404)
            return

        if path == "/me":
            raw_auth = self.headers.get("Authorization", "") or ""
            token = raw_auth[7:].strip() if raw_auth.lower().startswith("bearer ") else raw_auth.replace("Bearer ", "").strip()
            if not token:
                self._send_json({"error": "No token provided"}, 401)
                return
            try:
                from supabase_client import SupabaseClient

                db = SupabaseClient()
                user = db.verify_token(token)
                if not user:
                    self._send_json({"error": "Invalid token"}, 401)
                    return
                user_id = user.get("id")
                data = db.get_full_user_data(user_id)
                self._send_json({"user": user, "data": data})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/golden-records":
            raw_auth = self.headers.get("Authorization", "") or ""
            token = (
                raw_auth[7:].strip()
                if raw_auth.lower().startswith("bearer ")
                else raw_auth.replace("Bearer ", "").strip()
            )
            if not token:
                self._send_json({"error": "No token provided"}, 401)
                return
            try:
                from supabase_client import SupabaseClient

                db = SupabaseClient()
                user = db.verify_token(token)
                if not user:
                    self._send_json({"error": "Invalid token"}, 401)
                    return
                uid = user.get("id")
                rows = db.list_golden_records(uid) if uid else []
                self._send_json({"records": rows, "total": len(rows)})
            except Exception as e:
                log.warning("golden-records: %s", e)
                self._send_json({"error": str(e), "records": [], "total": 0}, 500)
            return

        if path == "/visit-packets":
            token = _bearer_token_from_headers(self.headers)
            if not token:
                self._send_json({"error": "No token provided"}, 401)
                return
            try:
                from supabase_client import SupabaseClient

                db = SupabaseClient()
                user = db.verify_token(token)
                if not user:
                    self._send_json({"error": "Invalid token"}, 401)
                    return
                uid = user.get("id")
                rows = db.list_visit_packets(uid) if uid else []
                self._send_json({"packets": rows, "total": len(rows)})
            except Exception as e:
                log.warning("visit-packets GET: %s", e)
                self._send_json({"error": str(e), "packets": [], "total": 0}, 500)
            return

        # Supplement Passport (standalone HTML page)
        if _want_passport(raw):
            html_path = _supplement_passport_file()
            if html_path:
                log.info("GET %s -> %s", self.path, html_path.name)
                self._send_html(html_path.read_text(encoding="utf-8"))
            else:
                log.error("supplement_passport.html missing; BASE_DIR=%s cwd=%s", BASE_DIR, Path.cwd())
                self._send_json(
                    {
                        "error": "supplement_passport.html not found",
                        "hint": f"Expect {BASE_DIR / 'supplement_passport.html'} beside Server.PY.",
                    },
                    404,
                )
            return

        # Visit Packet (patient → clinician summary)
        if _want_visit_packet(raw):
            html_path = _visit_packet_file()
            if html_path:
                log.info("GET %s -> %s", self.path, html_path.name)
                self._send_html(html_path.read_text(encoding="utf-8"))
            else:
                log.error("visit_packet.html missing; BASE_DIR=%s cwd=%s", BASE_DIR, Path.cwd())
                self._send_json(
                    {
                        "error": "visit_packet.html not found",
                        "hint": f"Expect {BASE_DIR / 'visit_packet.html'} beside Server.PY.",
                    },
                    404,
                )
            return

        # List all saved records
        if path == "/records":
            records = []
            for f in sorted(RECORDS_DIR.glob("golden_record_*.json"), reverse=True):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    records.append({
                        "file": f.name,
                        "product_name": data.get("product_name"),
                        "brand": data.get("brand"),
                        "overall_status": data.get("overall_status"),
                        "upc": data.get("upc"),
                        "dsld_id": data.get("dsld_id"),
                    })
                except Exception:
                    pass
            self._send_json({"records": records, "total": len(records)})
            return

        # Serve a specific record by filename
        if path.startswith("/record/"):
            fname = path.replace("/record/", "")
            fpath = RECORDS_DIR / fname
            if fpath.exists():
                self._send_json(json.loads(fpath.read_text(encoding="utf-8")))
            else:
                self._send_json({"error": f"Record not found: {fname}"}, 404)
            return

        if _is_med_check_api(path):
            self._send_json(
                {
                    "ok": True,
                    "endpoint": "POST /med-check",
                    "hint": "Send JSON: { medications, supplements, ingredients }",
                }
            )
            return

        log.warning("404 GET %s (normalized %s)", raw, path)
        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = _request_path(self.path)
        log.info("POST raw=%r normalized=%r", self.path, path)

        # Search iHerb products by text query
        if path == "/search-products":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}

                query = str(data.get("query", "")).strip()
                max_results = data.get("max_results", 8)
                try:
                    max_results = int(max_results)
                except (TypeError, ValueError):
                    max_results = 8
                max_results = max(1, min(max_results, 25))

                if not query:
                    self._send_json({"error": "query is required"}, 400)
                    return

                log.info("Search request: %s | max_results=%s", query, max_results)
                products = run_search_sync(query, max_results)
                self._send_json(
                    {
                        "query": query,
                        "count": len(products),
                        "products": products,
                        "results": products,
                    }
                )
            except Exception as e:
                log.error("Search products error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/sync-stack":
            token = _bearer_token_from_headers(self.headers)
            if not token:
                self._send_json({"error": "No token provided"}, 401)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}
                medications = data.get("medications") or []
                supplements = data.get("supplements") or []
                if not isinstance(medications, list) or not isinstance(supplements, list):
                    self._send_json({"error": "medications and supplements must be lists"}, 400)
                    return
                from supabase_client import SupabaseClient

                db = SupabaseClient()
                user = db.verify_token(token)
                if not user or not user.get("id"):
                    self._send_json({"error": "Invalid token"}, 401)
                    return
                uid = user["id"]
                n_meds = db.sync_medications(uid, medications)
                n_supps = db.sync_supplements(uid, supplements)
                self._send_json(
                    {
                        "ok": True,
                        "medications_synced": n_meds,
                        "supplements_synced": n_supps,
                    }
                )
            except Exception as e:
                log.error("sync-stack: %s", e)
                self._send_json({"error": str(e), "ok": False}, 500)
            return

        if path in ("/api/separation-schedule", "/separation-coach"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}
                user_routine = data.get("user_routine") if isinstance(data.get("user_routine"), dict) else None
                medications = data.get("medications")
                supplements = data.get("supplements")
                if medications is not None and not isinstance(medications, list):
                    self._send_json({"error": "medications must be a list"}, 400)
                    return
                if supplements is not None and not isinstance(supplements, list):
                    self._send_json({"error": "supplements must be a list"}, 400)
                    return

                token = _bearer_token_from_headers(self.headers)
                body_meds = medications if isinstance(medications, list) else []
                body_supps = supplements if isinstance(supplements, list) else []
                meds_list: list = []
                supps_list: list = []
                source = "local"

                if token:
                    from supabase_client import SupabaseClient

                    db = SupabaseClient()
                    user = db.verify_token(token)
                    if user and user.get("id"):
                        uid = user["id"]
                        db_meds = db.list_medications(uid)
                        db_supps = db.list_supplements(uid)
                        meds_list = db_meds if db_meds else body_meds
                        supps_list = db_supps if db_supps else body_supps
                        source = "supabase" if (db_meds or db_supps) else "local"
                    else:
                        meds_list, supps_list = body_meds, body_supps
                else:
                    meds_list, supps_list = body_meds, body_supps

                from separation_coach import generate_separation_schedule

                result = generate_separation_schedule(meds_list, supps_list, user_routine)
                out = result.to_json()
                out["source"] = source
                self._send_json(out)
            except Exception as e:
                log.error("Separation schedule error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/separation-schedule/from-golden-record":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}
                golden = data.get("golden_record") if isinstance(data.get("golden_record"), dict) else data
                if not isinstance(golden, dict) or not golden:
                    self._send_json({"error": "golden_record object is required"}, 400)
                    return
                user_routine = data.get("user_routine") if isinstance(data.get("user_routine"), dict) else None
                medications = data.get("medications") or []
                from separation_coach import schedule_from_golden_record

                result = schedule_from_golden_record(golden, medications, user_routine)
                self._send_json(result.to_json())
            except Exception as e:
                log.error("Separation schedule golden-record error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        # Med Check — curated interactions + RxNorm med resolution
        if _is_med_check_api(path):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}

                medications = data.get("medications") or []
                supplements = data.get("supplements") or []
                ingredients = data.get("ingredients") or []

                if not isinstance(medications, list) or not isinstance(supplements, list):
                    self._send_json({"error": "medications and supplements must be lists"}, 400)
                    return

                from med_check_engine import run_med_check

                result = run_med_check(medications, supplements, ingredients)
                self._send_json(result)
            except Exception as e:
                log.error("Med check error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/visit-packets":
            token = _bearer_token_from_headers(self.headers)
            if not token:
                self._send_json({"error": "No token provided"}, 401)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}
                snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else data
                if not isinstance(snapshot, dict) or not snapshot:
                    self._send_json({"error": "snapshot object is required"}, 400)
                    return
                from supabase_client import SupabaseClient

                db = SupabaseClient()
                user = db.verify_token(token)
                if not user:
                    self._send_json({"error": "Invalid token"}, 401)
                    return
                uid = user.get("id")
                row_id = db.save_visit_packet(uid, snapshot) if uid else None
                self._send_json({"ok": True, "id": row_id, "saved_to_cloud": bool(row_id)})
            except Exception as e:
                log.error("visit-packets POST: %s", e)
                self._send_json({"error": str(e), "saved_to_cloud": False}, 500)
            return

        # Run audit pipeline
        if path == "/audit":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}

                url = data.get("url", "").strip()
                upc = data.get("upc", "").strip() or None

                if not url:
                    self._send_json({"error": "url is required"}, 400)
                    return

                log.info("Audit request: %s | UPC: %s", url, upc or "none")
                result = run_pipeline_sync(url, upc)

                auth_header = (self.headers.get("Authorization") or "").strip()
                if result.get("error"):
                    log.info("Audit pipeline error — skipping cloud save")
                elif not auth_header:
                    log.warning("No Authorization header on /audit — not signed in or session missing")
                    result["saved_to_cloud"] = False
                    result["cloud_save_error"] = "not_signed_in"
                else:
                    token = auth_header.replace("Bearer ", "").replace("bearer ", "").strip()
                    try:
                        from supabase_client import SupabaseClient

                        db = SupabaseClient()
                        user = db.verify_token(token)
                        if user:
                            uid = user.get("id") or user.get("sub")
                            saved = db.save_golden_record(uid, result)
                            if saved:
                                result["saved_to_cloud"] = True
                                log.info("Saved to Supabase for user %s", uid)
                            else:
                                result["saved_to_cloud"] = False
                                result["cloud_save_error"] = "insert_failed"
                                log.warning("Supabase insert returned false")
                        else:
                            result["saved_to_cloud"] = False
                            result["cloud_save_error"] = "invalid_token"
                            log.warning("JWT verify failed — cloud save skipped")
                    except Exception as e:
                        log.warning("Supabase save failed: %s", e)
                        result["saved_to_cloud"] = False
                        result["cloud_save_error"] = str(e)

                self._send_json(result)

            except Exception as e:
                log.error("Audit error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        # Run multiple audits and rank value
        if path == "/audit-batch":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}
                items = data.get("items") or []

                if not items:
                    self._send_json({"error": "items is required (list of {url, upc?, price?, servings?})"}, 400)
                    return

                results = []
                errors = []
                for i, item in enumerate(items):
                    url = str(item.get("url", "")).strip()
                    upc = str(item.get("upc", "")).strip() or None
                    price = _safe_float(item.get("price"))
                    servings = _safe_float(item.get("servings"))

                    if not url:
                        errors.append({"index": i, "error": "url is required"})
                        continue

                    log.info("Batch audit %s/%s: %s", i + 1, len(items), url)
                    result = run_pipeline_sync(url, upc)
                    if result.get("error"):
                        errors.append({"index": i, "url": url, "error": result["error"]})
                        continue

                    if price is not None:
                        result["price"] = price
                    if servings is not None:
                        result["servings"] = int(servings)
                    else:
                        spc = result.get("servings_per_container")
                        parsed = _safe_float(spc)
                        result["servings"] = int(parsed) if parsed is not None and parsed > 0 else 30
                    results.append(result)

                ranked = _build_ranked_comparison(results)
                self._send_json(
                    {
                        "count_requested": len(items),
                        "count_success": len(results),
                        "count_failed": len(errors),
                        "errors": errors,
                        "records": results,
                        "comparison": {"ranked": ranked},
                    }
                )
            except Exception as e:
                log.error("Batch audit error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/shopping-agent":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}

                query = str(data.get("query", "")).strip()
                if not query:
                    self._send_json({"error": "query is required"}, 400)
                    return

                user_meds = data.get("medications") or []
                max_results = min(int(data.get("max_results", 6)), 10)

                token = _bearer_token_from_headers(self.headers)
                if token and not user_meds:
                    try:
                        from supabase_client import SupabaseClient

                        db = SupabaseClient()
                        user = db.verify_token(token)
                        if user and user.get("id"):
                            db_meds = db.list_medications(user["id"])
                            user_meds = [
                                str(m.get("medication_name") or m.get("name") or "")
                                for m in (db_meds or [])
                                if m.get("medication_name") or m.get("name")
                            ]
                    except Exception as e:
                        log.warning("Shopping agent — cloud meds: %s", e)

                if isinstance(user_meds, list):
                    user_meds = [str(m).strip() for m in user_meds if str(m).strip()]
                else:
                    user_meds = []

                from shopping_agent import parse_query, rank_products, get_fallback_products

                intent = parse_query(query)

                log.info("Shopping agent intent: %s", intent)

                products = []
                used_fallback = False
                data_source = "live"

                # 1) cache-first — fast, fresh, no scraping risk
                cache_products = _search_product_cache(intent, max_results)
                if cache_products and len(cache_products) >= 2:
                    products = cache_products
                    data_source = "cache"
                    log.info("Shopping agent: %d cache results", len(products))

                primary_search = intent.get("primary_search") or query
                if not products:
                    try:
                        live_results = run_search_sync(primary_search, max_results)
                        if live_results and len(live_results) > 0:
                            products = [_enrich_shopping_product(p) for p in live_results]
                            log.info(
                                "Shopping agent: %d live results for '%s'",
                                len(products),
                                primary_search,
                            )
                            products = [_quick_verify(p) for p in products]
                    except Exception as e:
                        log.warning("Shopping agent live search failed: %s", e)

                if not products or len(products) < 2:
                    products = get_fallback_products(intent)
                    used_fallback = True
                    data_source = "reference"
                    log.info("Shopping agent: using fallback catalog — %d products", len(products))

                if not products:
                    self._send_json({
                        "intent":        intent,
                        "candidates":    [],
                        "med_flags":     [],
                        "used_fallback": True,
                        "message":       (
                            f"No products found for '{query}'. "
                            "Try a more specific term like 'magnesium glycinate' or 'vitamin d3'."
                        ),
                    })
                    return

                result = rank_products(products, intent, user_meds)
                if not result.get("candidates") and products:
                    log.warning(
                        "Shopping agent: rank filtered all %d products — using fallback catalog",
                        len(products),
                    )
                    products = get_fallback_products(intent)
                    used_fallback = True
                    data_source = "reference"
                    result = rank_products(products, intent, user_meds)

                result["used_fallback"] = used_fallback
                result["data_source"] = data_source
                if used_fallback:
                    result["fallback_notice"] = (
                        "Live iHerb search is limited on your current Bright Data plan. "
                        "Showing curated products with verified iHerb links."
                    )
                self._send_json(result)

            except Exception as e:
                log.error("Shopping agent error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/basket-compare":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = json.loads(body) if body else {}

                supplements = data.get("supplements") or []
                if not isinstance(supplements, list) or len(supplements) < 2:
                    self._send_json(
                        {"error": "supplements must be a list of at least 2 items"}, 400
                    )
                    return

                supplements = [str(s).strip() for s in supplements if str(s).strip()][:8]

                from basket_compare import compare_basket
                import concurrent.futures

                def _search_one_supplement(supp: str) -> tuple[str, list]:
                    from shopping_agent import parse_query, rank_products, get_fallback_products

                    intent = parse_query(supp)
                    products = []
                    cached = _search_product_cache(intent, 3)
                    if cached:
                        products = cached
                    if not products:
                        try:
                            primary = intent.get("primary_search") or supp
                            live = run_search_sync(primary, 3)
                            if live and len(live) >= 1:
                                products = [dict(p, price_source="live") for p in live]
                        except Exception as e:
                            log.warning("Basket search error for '%s': %s", supp, e)
                    if not products:
                        products = get_fallback_products(intent)
                    if products:
                        result = rank_products(products, intent)
                        products = result.get("candidates") or products[:2]
                    return supp, products

                iherb_results: dict = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {
                        executor.submit(_search_one_supplement, supp): supp
                        for supp in supplements
                    }
                    for future in concurrent.futures.as_completed(futures):
                        supp, products = future.result()
                        iherb_results[supp] = products

                result = compare_basket(supplements, iherb_results)
                self._send_json(result)

            except Exception as e:
                log.error("Basket compare error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/ai-med-check":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length).decode()
                data   = json.loads(body) if body else {}
                query  = str(data.get("query", "")).strip()
                meds   = data.get("meds",  [])
                supps  = data.get("supps", [])
                if not query:
                    self._send_json({"error": "query is required"}, 400)
                    return
                from ai_med_check import ai_med_check
                result = ai_med_check(query, meds, supps)
                self._send_json(result)
            except Exception as e:
                log.error("AI Med Check error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/save-stack":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length).decode()
                data   = json.loads(body) if body else {}
                email  = str(data.get("email", "")).strip()
                meds   = data.get("meds",  [])
                supps  = data.get("supps", [])
                if not email or "@" not in email:
                    self._send_json({"error": "Valid email required"}, 400)
                    return
                from stack_save import save_stack, record_check
                from med_check_engine import run_med_check
                save_stack(email, meds, supps)
                result = run_med_check(meds, supps, [])
                record_check(email, meds, supps, result.get("interactions", []))
                self._send_json({
                    "saved": True,
                    "email": email,
                    "interactions": len(result.get("interactions", [])),
                })
            except Exception as e:
                log.error("save-stack error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/monitor-url":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length).decode()
                data   = json.loads(body) if body else {}
                from price_monitor import monitor_url
                result = monitor_url(
                    data.get("url", ""),
                    data.get("retailer", ""),
                    data.get("name", ""),
                    data.get("affiliate_tag"),
                )
                self._send_json(result)
            except Exception as e:
                log.error("monitor-url error: %s", e)
                self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"error": "Not found"}, 404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    server = HTTPServer((BIND, PORT), ElthioHandler)
    mc = _med_check_file()
    pp = _supplement_passport_file()
    vp = _visit_packet_file()
    log.info("=" * 55)
    log.info("  Elthio running on %s:%d", BIND, PORT)
    log.info("  Script: %s", Path(__file__).resolve())
    log.info("  PID: %s", os.getpid())
    log.info(
        "  Med Check GET /medcheck -> %s",
        mc if mc else f"MISSING (look for med_check.html next to Server.PY, BASE_DIR={BASE_DIR})",
    )
    log.info(
        "  Supplement Passport GET /passport -> %s",
        pp if pp else f"MISSING (look for supplement_passport.html, BASE_DIR={BASE_DIR})",
    )
    log.info(
        "  Visit Packet GET /visit-packet -> %s",
        vp if vp else f"MISSING (look for visit_packet.html, BASE_DIR={BASE_DIR})",
    )
    log.info("  Open in browser: http://127.0.0.1:%d  (or http://localhost:%d)", PORT, PORT)
    log.info("  API endpoint:    http://127.0.0.1:%d/audit", PORT)
    log.info("  Med Check API:   http://127.0.0.1:%d/med-check (POST)", PORT)
    log.info("  Separation Coach http://127.0.0.1:%d/api/separation-schedule (POST)", PORT)
    log.info("  Sync stack:        http://127.0.0.1:%d/api/sync-stack (POST + Bearer)", PORT)
    log.info("  Saved records:   http://127.0.0.1:%d/records", PORT)
    log.info("  Auth page:       http://127.0.0.1:%d/auth", PORT)
    log.info("  Supabase config: http://127.0.0.1:%d/config", PORT)
    log.info("  Session (JWT):   http://127.0.0.1:%d/me", PORT)
    log.info("  Cloud records:   http://127.0.0.1:%d/golden-records (GET + Bearer)", PORT)
    log.info("  Visit packets:   http://127.0.0.1:%d/visit-packets (GET/POST + Bearer)", PORT)
    log.info("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")


if __name__ == "__main__":
    main()