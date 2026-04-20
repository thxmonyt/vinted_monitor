import aiohttp
import asyncio
import json
import os

# ─────────────────────────────────────────
#  INSTELLINGEN — pas dit aan
# ─────────────────────────────────────────
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "JOUW_WEBHOOK_URL_HIER")

# Elektronica categorie IDs (pas aan naar wens)
# 1245 = Elektronica algemeen
# 2312 = Mobiele telefoons
# 2313 = Laptops & computers
# 2314 = Tablets
# 2315 = Spelconsoles
# 2316 = Camera's
# 1682 = Koptelefoons & audio
CATALOG_IDS = "1245"        # Elektronica algemeen (bevat alles)
COUNTRY_ID  = "16"          # Nederland = 16
CHECK_INTERVAL = 30         # seconden tussen checks

# ─────────────────────────────────────────
#  VINTED API URL
# ─────────────────────────────────────────
API_URL = (
    "https://www.vinted.nl/api/v2/catalog/items"
    f"?catalog_ids={CATALOG_IDS}"
    f"&country_ids={COUNTRY_ID}"
    "&order=newest_first"
    "&per_page=50"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

seen_ids: set[int] = set()


async def get_session_cookie(session: aiohttp.ClientSession) -> dict:
    """Haal een sessie cookie op van Vinted zodat de API werkt."""
    try:
        async with session.get("https://www.vinted.nl", headers=HEADERS) as r:
            return {c.key: c.value for c in session.cookie_jar}
    except Exception as e:
        print(f"[cookie] Fout: {e}")
        return {}


async def fetch_items(session: aiohttp.ClientSession) -> list[dict]:
    """Haal nieuwe listings op van de Vinted API."""
    try:
        async with session.get(API_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                print(f"[API] Status {r.status}")
                return []
            data = await r.json()
            return data.get("items", [])
    except Exception as e:
        print(f"[fetch] Fout: {e}")
        return []


def has_no_reviews(item: dict) -> bool:
    """Geeft True als de verkoper nog geen reviews heeft."""
    user = item.get("user", {})
    feedback_count = user.get("feedback_count", 0)
    return feedback_count == 0


async def send_to_discord(session: aiohttp.ClientSession, item: dict):
    """Stuur een embed naar Discord via de webhook."""
    title     = item.get("title", "Onbekend item")
    price     = item.get("price", {}).get("amount", "?")
    currency  = item.get("price", {}).get("currency_code", "EUR")
    condition = item.get("status", "Onbekend")
    url       = item.get("url", "")
    if not url.startswith("http"):
        url = "https://www.vinted.nl" + url

    # Foto
    photos    = item.get("photos", [])
    image_url = photos[0].get("url", "") if photos else ""

    # Verkoper info
    user      = item.get("user", {})
    seller    = user.get("login", "Onbekend")

    embed = {
        "title": title,
        "url": url,
        "color": 0x09B1BA,  # Vinted teal kleur
        "fields": [
            {"name": "💶 Prijs",    "value": f"€{price}",   "inline": True},
            {"name": "📦 Staat",    "value": condition,      "inline": True},
            {"name": "👤 Verkoper", "value": seller,         "inline": True},
            {"name": "⭐ Reviews",  "value": "Nog geen reviews", "inline": True},
            {"name": "🇳🇱 Land",   "value": "Nederland",    "inline": True},
        ],
        "footer": {"text": "Vinted Monitor • Elektronica NL"},
    }
    if image_url:
        embed["thumbnail"] = {"url": image_url}

    payload = {"embeds": [embed]}

    try:
        async with session.post(WEBHOOK_URL, json=payload) as r:
            if r.status not in (200, 204):
                print(f"[webhook] Status {r.status}: {await r.text()}")
    except Exception as e:
        print(f"[webhook] Fout: {e}")


async def main():
    print("🚀 Vinted Monitor gestart — Elektronica NL (geen reviews)")
    print(f"   Interval: elke {CHECK_INTERVAL} seconden\n")

    async with aiohttp.ClientSession() as session:
        # Eerst een sessie cookie ophalen
        await get_session_cookie(session)

        # Eerste run: sla bestaande items op zonder te pingen (geen spam bij start)
        print("🔄 Bestaande items laden...")
        items = await fetch_items(session)
        for item in items:
            seen_ids.add(item["id"])
        print(f"✅ {len(seen_ids)} bestaande items geladen. Nu live monitoren...\n")

        # Hoofdloop
        while True:
            await asyncio.sleep(CHECK_INTERVAL)

            items = await fetch_items(session)
            new_count = 0

            for item in items:
                item_id = item.get("id")
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Filter: alleen verkopers zonder reviews
                if not has_no_reviews(item):
                    continue

                await send_to_discord(session, item)
                new_count += 1
                print(f"📣 Nieuw item: {item.get('title')} — €{item.get('price', {}).get('amount')}")

            if new_count == 0:
                print(f"[{asyncio.get_event_loop().time():.0f}s] Geen nieuwe items.")


if __name__ == "__main__":
    asyncio.run(main())
