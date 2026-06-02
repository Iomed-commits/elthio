import asyncio
import nodriver as uc

async def scrape_supplement(url: str):
    browser = await uc.start()
    page = await browser.get(url)

    print("Waiting for page / Cloudflare...")
    await page.sleep(5)

    # Grab the page title so we know what we reached
    title_el = await page.select("h1")
    if title_el:
        print("Page H1:", title_el.text.strip())
    else:
        print("No <h1> found; might still be on a challenge page.")

    await browser.stop()

if __name__ == "__main__":
    target_url = "https://www.iherb.com/pr/now-foods-vitamin-d-3-high-potency-125-mcg-5-000-iu-240-softgels/22335"
    asyncio.run(scrape_supplement(target_url))