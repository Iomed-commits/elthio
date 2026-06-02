


import requests
from extractor import extract_supplement_label

API_KEY = "5085220d1748f50bbe6c3e3ed043aa0edb442957"

URLS = [
    "https://www.iherb.com/pr/now-foods-vitamin-d-3-high-potency-125-mcg-5-000-iu-240-softgels/22335",
    "https://www.lifeextension.com/vitamins-supplements/item02040/vitamins-d-and-k-with-sea-iodine",
    # add more product URLs here
]

def fetch_markdown(url: str) -> str:
    params = {
        "url": url,
        "apikey": API_KEY,
        "mode": "auto",
        "response_type": "markdown",
    }
    resp = requests.get("https://api.zenrows.com/v1/", params=params)
    resp.raise_for_status()
    return resp.text

if __name__ == "__main__":
    for url in URLS:
        print("\n=== URL ===")
        print(url)
        markdown = fetch_markdown(url)
        label = extract_supplement_label(markdown)
        print(label.model_dump())