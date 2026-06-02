"""Smoke test: ZenRows + iHerb (ZENROWS_API_KEY in .env)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


async def test() -> None:
    api_key = os.environ.get("ZENROWS_API_KEY", "")
    if not api_key:
        print("ERROR: ZENROWS_API_KEY not set")
        return

    print(f"Using key: {api_key[:8]}...")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.get(
            "https://api.zenrows.com/v1/",
            params={
                "apikey": api_key,
                "url": "https://www.iherb.com/pr/now-foods-vitamin-d-3-high-potency-125-mcg-5-000-iu-240-softgels/22335",
                "js_render": "true",
                "wait": "2000",
                "premium_proxy": "true",
            },
        )

    print(f"Status      : {r.status_code}")
    print(f"Chars       : {len(r.text):,}")
    print(f"Vitamin D   : {'Vitamin D' in r.text}")
    print(f"Supp Facts  : {'Supplement Facts' in r.text}")
    print(f"NOW Foods   : {'NOW Foods' in r.text}")

    if r.status_code != 200:
        print(f"\nError body  : {r.text[:300]}")


if __name__ == "__main__":
    asyncio.run(test())
