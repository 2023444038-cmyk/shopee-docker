import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth
import pandas as pd
import re


async def run_manual_scrape(target_url, limit_count=30):
    async with async_playwright() as p:
        print("🚀 Memulakan Stealth Browser (Chromium)...")

        # Launch browser. headless=True maksudnya dia lari kat background.
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", # Crucial for Docker/Render
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 🔥 PEMBETULAN KAT SINI: Guna stealth(page)
        await stealth(page)

        # 1. Cabut ID guna Regex
        match = re.search(r'i\.(\d+)\.(\d+)', target_url)
        if not match:
            print("❌ Error: Format link salah. Pastikan ada 'i.SHOPID.ITEMID'")
            await browser.close()
            return

        shop_id, item_id = match.group(1), match.group(2)
        print(f"📦 Target: Shop {shop_id} | Item {item_id}")

        # 2. Pergi ke link produk dulu untuk dapatkan 'Session Cookie' yang sah
        print(f"🔗 Melawat Shopee untuk bypass 403...")
        try:
            # Kita bagi timeout 60 saat sebab internet Malaysia kadang slow
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # Rehat kejap bagi cookie tu 'masak'
            await asyncio.sleep(3)

            # 3. Trigger API Shopee guna 'fetch' dalam context browser
            api_url = f"https://shopee.com.my/api/v2/item/get_ratings?filter=0&flag=1&itemid={item_id}&limit={limit_count}&offset=0&shopid={shop_id}&type=0"

            print("📡 Sedang menarik ulasan (Fetching Data)...")

            # Kita guna evaluate untuk 'pinjam' session browser tadi
            raw_response = await page.evaluate(f"""
                async () => {{
                    const response = await fetch('{api_url}');
                    return await response.json();
                }}
            """)

            await browser.close()

            # 4. Simpan ke CSV
            if 'data' in raw_response and raw_response['data']['ratings']:
                reviews_list = []
                for r in raw_response['data']['ratings']:
                    if r.get('comment'):
                        reviews_list.append({
                            "Review_Text": r['comment'].replace('\n', ' '),
                            "Rating_Star": r['rating_star']
                        })

                df = pd.DataFrame(reviews_list)
                df.to_csv("scraped_reviews.csv", index=False, encoding='utf-8-sig')

                print("-" * 30)
                print(f"✅ BERJAYA! {len(df)} ulasan disimpan ke 'scraped_reviews.csv'")
                print("-" * 30)
            else:
                print("❌ Gagal: Shopee sekat atau tiada ulasan dijumpai.")

        except Exception as e:
            print(f"❌ Error semasa scraping: {e}")
            await browser.close()


if __name__ == "__main__":
    # LINK PRODUK KAU
    URL_PRODUK = "https://shopee.com.my/NEW%E3%80%90-199-Speed-%E3%80%91-Rechargeable-Mini-Small-Fan-100-199-Wind-Speeds-Handheld-Super-Mute-High-Wind-Power-Desktop-Turbo-Fan-i.1276527157.29484775921"

    asyncio.run(run_manual_scrape(URL_PRODUK, limit_count=30))