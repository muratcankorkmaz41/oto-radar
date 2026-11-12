import asyncio
import sys
from scraper import ArabamScraper, damage_ok
from database import Database
from notifier import TelegramNotifier
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CHECK_INTERVAL_SECONDS,
    DEAL_DISCOUNT_THRESHOLD, PAGES_PER_FILTER, MAX_DETAIL_PER_ROUND,
)

# Ağır hasar bilgisi girilmemiş ilanlar "ağır hasar kayıtsız" sayılsın mı?
AGIR_HASAR_BELIRTILMEMIS_KABUL = True

# Boya/değişen bilgisi girilmemiş ilanlar (Boyasız / Değişensiz switch'i açıkken) geçsin mi?
BOYA_BELIRTILMEMIS_KABUL = False

# Fırsat hesabı için en az kaç geçerli fiyat gerekli (az ilanla ortalama anlamsız olur)
MIN_PRICES_FOR_AVG = 5


def mark_deals(listings: list):
    """Aynı aramadaki ilanların ortalama fiyatına göre, ortalamadan
    DEAL_DISCOUNT_THRESHOLD kadar ucuz olanları 'fırsat' olarak işaretler."""
    prices = [ad["price"] for ad in listings if ad["price"] > 0]
    if len(prices) < MIN_PRICES_FOR_AVG:
        return 0
    avg = sum(prices) / len(prices)
    for ad in listings:
        ad["avg_price"] = int(avg)
        ad["is_deal"] = ad["price"] > 0 and ad["price"] <= avg * (1 - DEAL_DISCOUNT_THRESHOLD)
        if ad["is_deal"]:
            ad["discount_pct"] = round((1 - ad["price"] / avg) * 100)
    return int(avg)


async def process_filter(flt, db: Database, scraper: ArabamScraper, notifier: TelegramNotifier):
    print(f"\n[*] Taranıyor: {flt['keyword']}")
    listings = await scraper.fetch_listings(flt["keyword"], pages=PAGES_PER_FILTER)

    if not listings:
        print(f"[-] İlan bulunamadı veya sayfa yüklenemedi. (Filtre: {flt['keyword']})")
        return

    avg = mark_deals(listings)
    avg_text = f", ortalama fiyat {avg:,} TL".replace(",", ".") if avg else ""
    print(f"[+] Siteden {len(listings)} adet ilan yakalandı{avg_text}.")

    # 1) Ucuz kontroller: yeni mi, fiyat/km/yıl uygun mu
    candidates = []
    sayac = {"kayıtlı": 0, "fiyat": 0, "km": 0, "yıl": 0, "elenmiş": 0}
    for ad in listings:
        if not db.is_new_listing(ad["id"]):
            sayac["kayıtlı"] += 1
            continue
        if flt["max_price"] > 0 and (ad["price"] <= 0 or ad["price"] > flt["max_price"]):
            sayac["fiyat"] += 1
            continue
        if flt["max_km"] > 0 and ad["km"] > flt["max_km"]:
            sayac["km"] += 1
            continue
        if flt["min_year"] > 0 and ad["year"] > 0 and ad["year"] < flt["min_year"]:
            sayac["yıl"] += 1
            continue
        if db.is_rejected(flt["id"], ad["id"]):
            sayac["elenmiş"] += 1
            continue
        candidates.append(ad)

    print(f"[i] {len(listings)} ilandan: zaten kayıtlı {sayac['kayıtlı']}, "
          f"fiyat {sayac['fiyat']}, km {sayac['km']}, yıl {sayac['yıl']} "
          f"ve önceden elenen {sayac['elenmiş']} ilan çıktı, aday: {len(candidates)}")

    # 2) Hasar switch'i açıksa gerçek bilgiyi ilan sayfasından oku
    needs_detail = bool(flt["req_boyasiz"] or flt["req_degisensiz"] or flt["req_hasarsiz"])
    if needs_detail and candidates:
        if len(candidates) > MAX_DETAIL_PER_ROUND:
            print(f"[i] {len(candidates) - MAX_DETAIL_PER_ROUND} aday sonraki tura bırakıldı.")
        candidates = candidates[:MAX_DETAIL_PER_ROUND]
        print(f"[*] {len(candidates)} aday ilanın detay sayfası kontrol ediliyor...")
        await scraper.fetch_details(candidates)

    # 3) Karar ver ve bildir
    for ad in candidates:
        if ad.get("removed"):
            db.add_rejected(flt["id"], ad["id"])
            print(f"[-] İlan yayından kalkmış, atlandı: {ad['title'][:60]}")
            continue
        if needs_detail:
            ok, reason = damage_ok(
                flt, ad,
                accept_unspecified=BOYA_BELIRTILMEMIS_KABUL,
                accept_agir_unspecified=AGIR_HASAR_BELIRTILMEMIS_KABUL,
            )
            if ok is None:
                print(f"[?] {ad['id']}: {reason}, sonraki turda tekrar denenecek.")
                continue
            if not ok:
                db.add_rejected(flt["id"], ad["id"])
                print(f"[-] Elendi ({reason}) [ağır={ad.get('agir_hasarli')}, boya={ad.get('boya_degisen')}]: {ad['title'][:60]}")
                print(f"    {ad['url']}")
                continue

        etiket = " [FIRSAT]" if ad.get("is_deal") else ""
        print(f"[UYGUN ARAÇ BULUNDU]{etiket} {ad['title']} - {ad['year']} Model - {ad['km']:,} KM")
        sent = await notifier.send_listing_alert(ad)
        if not sent:
            continue  # Mesaj gitmediyse kaydetme, sonraki turda tekrar denenir
        db.insert_listing(ad)
        await asyncio.sleep(1)


async def run_bot():
    db = Database()
    notifier = TelegramNotifier(token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    if not notifier.enabled:
        print("[!] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID .env'de yok: bildirim gönderilmeyecek, "
              "sadece ilanlar kaydedilecek.")

    print("[*] Gelişmiş Hassas Radar Botu devrede...")

    # Hata analizi için tarayıcıyı görmek istersen headless=False yapabilirsin
    async with ArabamScraper(headless=True) as scraper:
        while True:
            active_filters = db.get_all_filters()
            if not active_filters:
                print("[i] Aktif filtre yok, panelden (python app.py) filtre ekle.")
                await asyncio.sleep(30)
                continue

            for flt in active_filters:
                try:
                    await process_filter(flt, db, scraper, notifier)
                except Exception as e:
                    # Bir filtredeki hata diğer filtrelerin taranmasını engellemesin
                    print(f"[!] Hata ({flt['keyword']}): {type(e).__name__}: {e}")

            print(f"[*] Tarama turu bitti. {CHECK_INTERVAL_SECONDS} saniye sonra tekrar edilecek...")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Windows konsolu ilan başlığındaki emojileri yazamayınca bot çökmesin
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n[*] Bot durduruldu.")
