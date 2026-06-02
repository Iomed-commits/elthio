import requests
import json

BASE_URL = "https://api.ods.od.nih.gov/dsld/v9"
DEBUG = True


def search_products(product_name: str):
    url = f"{BASE_URL}/search-filter"
    params = {"q": product_name, "size": 5, "status": 1}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if DEBUG:
            print("\n[DEBUG] URL:", r.url)
            print("[DEBUG] Keys:", list(data.keys()))
            print("[DEBUG] First hit:\n", json.dumps(data.get("hits", [])[:1], indent=2)[:800])
        results = []
        for hit in data.get("hits", []):
            src = hit.get("_source", {})
            results.append({"id": hit.get("_id") or src.get("id"), "name": src.get("fullName"), "brand": src.get("brandName")})
        return [p for p in results if p["id"]]
    except Exception as e:
        print(f"Search Error: {e}")
        return []


def get_label(label_id: str):
    url = f"{BASE_URL}/label/{label_id}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if DEBUG:
            print("\n[DEBUG] Label keys:", list(data.keys()))
            print("[DEBUG] First 2 rows:\n", json.dumps(data.get("ingredientRows", [])[:2], indent=2)[:800])
        return data
    except Exception as e:
        print(f"Label Error: {e}")
        return None


def parse_ingredients(label: dict):
    rows = label.get("ingredientRows", [])
    if not rows:
        print("No ingredients found. Keys:", list(label.keys()))
        return
    print("\n" + "-"*55)
    print(f"  {'INGREDIENT':<35} {'AMOUNT':>8}  UNIT")
    print("-"*55)
    for row in rows:
        name = row.get("name", "Unknown")
        qty = row.get("quantity", [])
        if qty:
            amount = qty[0].get("quantity", "N/A")
            unit = qty[0].get("unit", "")
        else:
            amount, unit = "N/A", ""
        print(f"  {name:<35} {str(amount):>8}  {unit}")
    print("-"*55)


def lookup_product(product_name: str):
    print(f"\nQuerying NIH DSLD for: {product_name}")
    products = search_products(product_name)
    if not products:
        print("No products found.")
        return
    for i, p in enumerate(products):
        print(f"  [{i}] {p['name']}  |  {p['brand']}  |  ID: {p['id']}")
    product = products[0]
    print(f"\nUsing: {product['name']} ({product['brand']})")
    label = get_label(product["id"])
    if label:
        parse_ingredients(label)
    else:
        print("Could not retrieve label.")


if __name__ == "__main__":
    lookup_product("Nature Made Vitamin D3")