
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict

from config import get_config
from crawler import crawl_page, screenshot_page
from extractor import extract_supplement_label
from vision_extractor import extract_supplement_label_from_image


async def run_audit(
    url: str, wait_for_selector: str | None = None, use_vision: bool = False
) -> Dict[str, Any]:
    """
    Orchestrate the crawl + extraction pipeline for a single product URL.

    Returns a plain dict that can be sent to NIH DSLD comparison utilities.
    """

    # Ensure config is loaded and API key is present early.
    get_config()

    if use_vision:
        image_path = await screenshot_page(url)
        label = extract_supplement_label_from_image(image_path)
    else:
        markdown = await crawl_page(url, wait_for_selector=wait_for_selector)
        label = extract_supplement_label(markdown)

    # Convert Pydantic model to plain dict ready for further use.
    return label.model_dump()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supplement Label Auditor")
    parser.add_argument("url", help="Product detail page URL to audit.")
    parser.add_argument(
        "--wait-for",
        dest="wait_for",
        default=None,
        help=(
            "Optional CSS selector that indicates the main product content has loaded. "
            "Useful for pages that render content dynamically."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the extracted label JSON.",
    )
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Use OpenAI vision on a screenshot instead of text-only extraction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result = asyncio.run(
        run_audit(args.url, wait_for_selector=args.wait_for, use_vision=bool(args.vision))
    )

    if args.pretty:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()

