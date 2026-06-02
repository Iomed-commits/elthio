"""
Elthio — Supabase client for Python.

Uses SUPABASE_URL and SUPABASE_ANON_KEY from the environment (optionally loaded
from .env via python-dotenv when calling the helpers below).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

log = logging.getLogger("elthio.supabase")


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


def normalize_supabase_url(raw: str | None) -> str:
    """Strip /rest/v1 so the URL matches what supabase-js and create_client expect."""
    u = (raw or "").strip().rstrip("/")
    i = u.find("/rest/v1")
    if i != -1:
        u = u[:i].rstrip("/")
    return u


def get_supabase_url() -> str:
    _load_dotenv_if_present()
    return normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))


def get_supabase_anon_key() -> str:
    _load_dotenv_if_present()
    return (os.environ.get("SUPABASE_ANON_KEY", "") or "").strip()


def create_supabase_client() -> Client:
    """Return a Supabase client using the public anon key (RLS applies)."""
    from supabase import create_client

    url = get_supabase_url()
    key = get_supabase_anon_key()
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    return create_client(url, key)


def _user_to_dict(user) -> dict:
    if user is None:
        return {}
    if hasattr(user, "model_dump"):
        return user.model_dump()
    if hasattr(user, "dict"):
        return user.dict()
    if isinstance(user, dict):
        return user
    uid = getattr(user, "id", None)
    return {"id": str(uid) if uid is not None else None, "email": getattr(user, "email", None)}


def _user_scoped_supabase_client(jwt: str):
    """Supabase client that runs PostgREST as the signed-in user (RLS)."""
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions

    anon = get_supabase_anon_key()
    opts = SyncClientOptions()
    opts.headers = {
        **opts.headers,
        "apiKey": anon,
        "Authorization": f"Bearer {jwt}",
    }
    return create_client(get_supabase_url(), anon, opts)


class SupabaseClient:
    """Server-side Supabase access: verify JWTs and load user-scoped rows."""

    def __init__(self) -> None:
        self._client = create_supabase_client()
        self._verified_jwt: str | None = None

    @property
    def client(self) -> "Client":
        """Underlying Supabase client (anon key)."""
        return self._client

    def verify_token(self, token: str) -> dict | None:
        self._verified_jwt = None
        token = (token or "").strip()
        if not token:
            return None
        try:
            response = self._client.auth.get_user(token)
            if response is None or response.user is None:
                return None
            self._verified_jwt = token
            return _user_to_dict(response.user)
        except Exception as e:
            log.warning("verify_token failed: %s", e)
            return None

    def get_full_user_data(self, user_id: str) -> dict:
        """
        Extra profile rows for the user. Uses the last verified JWT so PostgREST
        runs as that user (RLS). Tries `profiles`; returns {"profiles": null} if missing.
        """
        out: dict = {"profiles": None}
        if not user_id or not self._verified_jwt:
            return out
        try:
            user_client = _user_scoped_supabase_client(self._verified_jwt)
            res = (
                user_client.table("profiles")
                .select("*")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if res.data is not None:
                out["profiles"] = res.data
        except Exception:
            out["profiles"] = None
        return out

    def save_golden_record(self, user_id: str, record: dict) -> bool:
        """
        Insert one Golden Record for the authenticated user.

        Expects a public.golden_records table, e.g.:

            create table public.golden_records (
              id uuid primary key default gen_random_uuid(),
              user_id uuid not null references auth.users (id) on delete cascade,
              record jsonb not null,
              created_at timestamptz not null default now()
            );
            alter table public.golden_records enable row level security;
            create policy golden_records_insert_own on public.golden_records
              for insert to authenticated with check (auth.uid() = user_id);
            create policy golden_records_select_own on public.golden_records
              for select to authenticated using (auth.uid() = user_id);
        """
        if not user_id or not self._verified_jwt:
            raise ValueError("save_golden_record requires a verified user JWT")
        user_client = _user_scoped_supabase_client(self._verified_jwt)
        # Strip server-only keys; keep full audit payload in jsonb
        payload = {
            k: v
            for k, v in record.items()
            if k not in ("saved_to_cloud", "cloud_save_error")
        }
        safe_record = json.loads(json.dumps(payload, default=str))
        row = {
            "user_id": user_id,
            "record": safe_record,
            # Denormalized columns (optional — some Supabase tables define these for Table Editor)
            "product_name": safe_record.get("product_name"),
            "brand": safe_record.get("brand"),
            "upc": safe_record.get("upc"),
            "dsld_id": safe_record.get("dsld_id"),
            "overall_status": safe_record.get("overall_status"),
            "source_url": safe_record.get("source_url"),
        }
        try:
            user_client.table("golden_records").insert(row).execute()
        except Exception as e:
            err = str(e)
            if "PGRST204" in err or "column" in err.lower():
                user_client.table("golden_records").insert(
                    {"user_id": user_id, "record": safe_record}
                ).execute()
            else:
                raise
        return True

    def list_golden_records(self, user_id: str, *, limit: int = 40) -> list[dict]:
        """List recent golden_records for this user (uses verified JWT for RLS)."""
        if not self._verified_jwt or not user_id:
            return []
        user_client = _user_scoped_supabase_client(self._verified_jwt)
        res = (
            user_client.table("golden_records")
            .select("id, created_at, record")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])

    def save_visit_packet(self, user_id: str, snapshot: dict) -> str | None:
        """Insert one Visit Packet snapshot for the authenticated user. Returns row id."""
        if not user_id or not self._verified_jwt:
            raise ValueError("save_visit_packet requires a verified user JWT")
        user_client = _user_scoped_supabase_client(self._verified_jwt)
        safe = json.loads(json.dumps(snapshot, default=str))
        row = {
            "user_id": user_id,
            "snapshot": safe,
            "patient_name": (safe.get("patient_name") or "")[:200] or None,
            "visit_date": (safe.get("visit_date") or "")[:120] or None,
        }
        res = user_client.table("visit_packets").insert(row).execute()
        data = res.data
        if isinstance(data, list) and data and data[0].get("id"):
            return str(data[0]["id"])
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        return None

    def list_visit_packets(self, user_id: str, *, limit: int = 30) -> list[dict]:
        """List recent visit_packets for this user."""
        if not self._verified_jwt or not user_id:
            return []
        user_client = _user_scoped_supabase_client(self._verified_jwt)
        res = (
            user_client.table("visit_packets")
            .select("id, created_at, patient_name, visit_date, snapshot")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])

    def list_medications(self, user_id: str, *, limit: int = 100) -> list[dict]:
        """User medications for Separation Coach (requires medications table + RLS)."""
        if not self._verified_jwt or not user_id:
            return []
        try:
            user_client = _user_scoped_supabase_client(self._verified_jwt)
            res = (
                user_client.table("medications")
                .select("id, name, dose, notes, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(res.data or [])
        except Exception as e:
            log.warning("list_medications: %s", e)
            return []

    def list_supplements(self, user_id: str, *, limit: int = 100) -> list[dict]:
        """User supplements for Separation Coach (requires supplements table + RLS)."""
        if not self._verified_jwt or not user_id:
            return []
        try:
            user_client = _user_scoped_supabase_client(self._verified_jwt)
            res = (
                user_client.table("supplements")
                .select("id, name, brand, ingredients, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(res.data or [])
        except Exception as e:
            log.warning("list_supplements: %s", e)
            return []

    def sync_medications(self, user_id: str, medications: list) -> int:
        """Replace user's medication rows with the given list (names or dicts with name)."""
        if not self._verified_jwt or not user_id:
            raise ValueError("sync_medications requires a verified user JWT")
        user_client = _user_scoped_supabase_client(self._verified_jwt)
        names: list[str] = []
        seen: set[str] = set()
        for item in medications or []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("medication") or "").strip()
            else:
                name = str(item or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
        try:
            user_client.table("medications").delete().eq("user_id", user_id).execute()
        except Exception as e:
            log.warning("sync_medications delete: %s", e)
        if not names:
            return 0
        rows = [{"user_id": user_id, "name": n} for n in names]
        user_client.table("medications").insert(rows).execute()
        return len(rows)

    def sync_supplements(self, user_id: str, supplements: list) -> int:
        """Replace user's supplement rows with the given list."""
        if not self._verified_jwt or not user_id:
            raise ValueError("sync_supplements requires a verified user JWT")
        user_client = _user_scoped_supabase_client(self._verified_jwt)
        rows: list[dict] = []
        seen: set[str] = set()
        for item in supplements or []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("product_name") or "").strip()
                brand = str(item.get("brand") or "").strip() or None
                ingredients = str(item.get("ingredients") or item.get("form") or "").strip() or None
            else:
                name = str(item or "").strip()
                brand = None
                ingredients = None
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "user_id": user_id,
                    "name": name,
                    "brand": brand,
                    "ingredients": ingredients,
                }
            )
        try:
            user_client.table("supplements").delete().eq("user_id", user_id).execute()
        except Exception as e:
            log.warning("sync_supplements delete: %s", e)
        if not rows:
            return 0
        user_client.table("supplements").insert(rows).execute()
        return len(rows)
