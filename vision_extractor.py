from __future__ import annotations

import base64
import json
import os
from typing import List

from openai import OpenAI

from config import get_config
from extractor import SupplementLabel


def _image_to_data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def extract_supplement_label_from_image(image_path: str) -> SupplementLabel:
    """
    Use an OpenAI vision-capable model to read a supplement label image and
    return a populated SupplementLabel.
    """

    cfg = get_config()
    client = OpenAI(api_key=cfg.openai_api_key)

    data_url = _image_to_data_url(image_path)

    prompt = (
        "You are an expert at reading dietary supplement labels from a screenshot of a product page. "
        "The image may show a full webpage; find the Supplement Facts box/table (often in a black-bordered panel).\n\n"
        "Extract:\n"
        "- brand: manufacturer (e.g. Life Extension)\n"
        "- product_name: product name from the page or label\n"
        "- serving_size: the exact 'Serving Size' line from Supplement Facts (e.g. '1 capsule', '2 softgels')\n"
        "- ingredients_list: list EVERY line from the Supplement Facts table—each vitamin, mineral, and ingredient with its amount and unit (e.g. 'Vitamin D3 (as cholecalciferol) 75 mcg (3000 IU)')\n"
        "- citations_found: any study references or citations on the label\n\n"
        "If you see a Supplement Facts panel, serving_size and ingredients_list must NOT be empty. "
        "Include every row from the facts table in ingredients_list.\n\n"
        "Return ONLY valid JSON, no markdown or explanation:\n"
        '{"brand": "", "product_name": "", "serving_size": "", "ingredients_list": [], "citations_found": []}'
    )

    # Vision-capable model (gpt-4o-mini supports images)
    model = cfg.model_name if "gpt-4o" in cfg.model_name or "gpt-4-turbo" in cfg.model_name else "gpt-4o-mini"

    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )

    raw = completion.choices[0].message.content or ""

    if os.environ.get("DEBUG_VISION"):
        print("DEBUG vision raw response:", raw[:500] + ("..." if len(raw) > 500 else ""), file=__import__("sys").stderr)

    # Be tolerant of code fences if the model adds them.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()

    data = json.loads(cleaned)
    return SupplementLabel(**data)


__all__ = ["extract_supplement_label_from_image"]

