import asyncio
import os
import aiohttp
import requests

# ─────────────────────────────────────────
#  INSTELLINGEN — zet dit in Railway Variables
# ─────────────────────────────────────────
WEBHOOK_URL    = os.environ.get("DISCORD_WEBHOOK", "")
VINTED_COOKIE  = os.environ.get("VINTED_COOKIE", "")   # access_token_web waarde
CHECK_INTERVAL = 30

CATALOG_ID  = "1245"  # Elektronica algemeen
COUNTRY_ID  = "16"    # Nederland
BASE_URL    = "https://www.vinted.nl"

seen_ids: set[str] = set()

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Referer":         "https://www.vinted.nl/catalog",
}

def get_cookies() -> dict:
    return {"access_token_web": VINTED_COOKIE} if VINTED_COOKIE else {}


def fetch_items() -> list:
    try:
        r = requests.get(
            f"{BASE_URL}/api/v2/catalog/items",
            params={
                "catalog_ids": CATALOG_ID,
                "country_ids": COUNTRY_ID,
                "order":       "newest_first",
                "per_page":    "96",
            },
            headers=HEADERS,
            cookies=get_cookies(),
            timeout=15,
        )
        if r.status_code == 401:
            print("⚠️  Cookie verlopen! Update VINTED_COOKIE in Railway Variables.")
            return []
        if r.status_code != 200:
            print(f"[API] Status {r.status_code}")
            return []
        return r.json().get("items", [])
    except Exception as e:
        print(f"[fetch] Fout: {e}")
        return []


def fetch_user(user_id: str) -> dict | None:
    try:
        r = requests.get(
            f"{BASE_URL}/api/v2/users/{user_id}",
            headers=HEADERS,
            cookies=get_cookies(),
            timeout=10,
        )
        if r.status_code != 200:
            return None
        u = r.json().get("user", {})
        return {
            "country":  (u.get("country_iso_code") or "").upper(),
            "posCount": int(u.get("positive_feedback_count") or 0),
        }
    except Exception as e:
        print(f"[user] Fout: {e}")
        return None


def is_match(item: dict) -> bool:
    user_id = str(item.get("user", {}).get("id", ""))
    if not user_id:
        return False
    user = fetch_user(user_id)
    if not user:
        return False
    return user["country"] == "NL" and user["posCount"] == 0


async def send_discord(session: aiohttp.ClientSession, item: dict):
    title     = item.get("title", "Onbekend")
    price     = item.get("price", {}).get("amount", "?")
    url       = item.get("url", "")
    if url and not url.startswith("http"):
        url = BASE_URL + url
    seller    = item.get("user", {}).get("login", "Onbekend")
    photos    = item.get("photos", [])
    image_url = photos[0].get("url", "") if photos else ""

    embed = {
        "title": title,
        "url":   url,
        "color": 0x09B1BA,
        "fields": [
            {"name": "💶 Prijs",    "value": f"€{price}",    "inline": True},
            {"name": "👤 Verkoper", "value": seller,          "inline": True},
            {"name": "⭐ Reviews",  "value": "Geen reviews",  "inline": True},
            {"name": "🇳🇱 Land",   "value": "Nederland",     "inline": True},
        ],
        "footer": {"text": "Vinted Monitor • Elektronica NL"},
    }
    if image_url:
        embed["thumbnail"] = {"url": image_url}

    try:
        async with session.post(WEBHOOK_URL, json={"embeds": [embed]}) as r:
            if r.status not in (200, 204):
                print(f"[webhook] Status {r.status}")
            else:
                print(f"📣 Verstuurd naar Discord: {title} — €{price}")
    except Exception as e:
        print(f"[discord] Fout: {e}")


async def main():
    print("🚀 Vinted Monitor gestart — Elektronica NL (geen reviews)")
    print(f"   Cookie aanwezig: {'✅' if VINTED_COOKIE else '❌ VINTED_COOKIE niet ingesteld!'}")
    print(f"   Webhook aanwezig: {'✅' if WEBHOOK_URL else '❌ DISCORD_WEBHOOK niet ingesteld!'}")
    print(f"   Interval: elke {CHECK_INTERVAL} seconden\n")

    async with aiohttp.ClientSession() as session:
        print("🔄 Bestaande items laden (geen spam bij start)...")
        for item in fetch_items():
            seen_ids.add(str(item.get("id")))
        print(f"✅ {len(seen_ids)} bestaande items geladen. Nu live monitoren...\n")

        while True:
            await asyncio.sleep(CHECK_INTERVAL)

            for item in fetch_items():
                item_id = str(item.get("id"))
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                title = item.get("title", item_id)
                print(f"🔍 Nieuw item: {title} — verkoper checken...")

                if is_match(item):
                    await send_discord(session, item)
                else:
                    print(f"   ↳ Niet NL of heeft reviews — overgeslagen")


if __name__ == "__main__":
    asyncio.run(main())
