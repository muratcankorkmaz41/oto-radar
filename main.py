import asyncio
import re
from scraper import ArabamScraper, damage_ok
from database import Database
from notifier import TelegramNotifier
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CHECK_INTERVAL_SECONDS

# Her turda en fazla kaç ilanın detay sayfası açılsın (fazlası sonraki tura kalır)
MAX_DETAIL_PER_ROUND = 15

# Ağır hasar bilgisi girilmemiş ilanlar "ağır hasar kayıtsız" sayılsın mı?
AGIR_HASAR_BELIRTILMEMIS_KABUL = True

# Boya/değişen bilgisi girilmemiş ilanlar (Boyasız / Değişensiz switch'i açıkken) geçsin mi?
BOYA_BELIRTILMEMIS_KABUL = False


def build_search_url(keyword: str) -> str:
    tr_map = str.maketrans("üışçöğÜIŞÇÖĞ", "uiscogUISCOG")
    clean = keyword.translate(tr_map).lower()
    clean = re.sub(r'[^a-z0-9\s-]', '', clean)
    clean = re.sub(r'\s+', '-', clean.strip())
    return f"https://www.arabam.com/ikinci-el/otomobil/{clean}"


async def run_bot():
    db = Database()
    notifier = TelegramNotifier(token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    # Hata analizi için arkada çalışan tarayıcıyı görebilmek istersen headless=False yapabilirsin
    scraper = ArabamScraper(headless=True)

    # Hasar filtresine takılan ilanları tekrar tekrar açmamak için (bot kapanınca sıfırlanır)
    rejected = set()

    print("[*] Gelişmiş Hassas Radar Botu devrede...")

    while True:
        try:
            active_filters = db.get_all_filters()

            if not active_filters:
                await asyncio.sleep(10)
                continue

            for flt in active_filters:
                search_url = build_search_url(flt["keyword"])
                print(f"\n[*] Taranıyor: {flt['keyword']} -> {search_url}")

                # İlanları çek ve sayısını hemen yazdır
                listings = await scraper.fetch_listings(search_url)

                if not listings:
                    print(f"[-] İlan bulunamadı veya sayfa yüklenemedi. (Filtre: {flt['keyword']})")
                    continue

                print(f"[+] Siteden {len(listings)} adet ilan yakalandı.")

                # 1) Ucuz kontroller: yeni mi, fiyat/km/yıl uygun mu
                candidates = []
                sayac = {"kayıtlı": 0, "fiyat": 0, "km": 0, "yıl": 0, "elenmiş": 0}
                for ad in listings:
                    if not db.is_new_listing(ad["id"]):
                        sayac["kayıtlı"] += 1
                        continue
                    if flt["max_price"] > 0 and ad["price"] > flt["max_price"]:
                        sayac["fiyat"] += 1
                        continue
                    if flt["max_km"] > 0 and ad["km"] > 0 and ad["km"] > flt["max_km"]:
                        sayac["km"] += 1
                        continue
                    if flt["min_year"] > 0 and ad["year"] > 0 and ad["year"] < flt["min_year"]:
                        sayac["yıl"] += 1
                        continue
                    if (flt["id"], ad["id"]) in rejected:
                        sayac["elenmiş"] += 1
                        continue
                    candidates.append(ad)

                print(f"[i] {len(listings)} ilandan: zaten kayıtlı {sayac['kayıtlı']}, "
                      f"fiyat {sayac['fiyat']}, km {sayac['km']}, yıl {sayac['yıl']} "
                      f"ve önceden elenen {sayac['elenmiş']} ilan çıktı, aday: {len(candidates)}")

                # 2) Hasar switch'i açıksa gerçek bilgiyi ilan sayfasından oku
                needs_detail = bool(flt["req_boyasiz"] or flt["req_degisensiz"] or flt["req_hasarsiz"])
                if needs_detail and candidates:
                    candidates = candidates[:MAX_DETAIL_PER_ROUND]
                    print(f"[*] {len(candidates)} aday ilanın detay sayfası kontrol ediliyor...")
                    await scraper.fetch_details(candidates)

                # 3) Karar ver ve bildir
                for ad in candidates:
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
                            rejected.add((flt["id"], ad["id"]))
                            print(f"[-] Elendi ({reason}) [ağır={ad.get('agir_hasarli')}, boya={ad.get('boya_degisen')}]: {ad['title'][:60]}")
                            print(f"    {ad['url']}")
                            continue

                    print(f"[UYGUN ARAÇ BULUNDU] {ad['title']} - {ad['year']} Model - {ad['km']:,} KM")
                    sent = await notifier.send_listing_alert(ad)
                    if not sent:
                        continue  # Mesaj gitmediyse kaydetme, sonraki turda tekrar denenir
                    await asyncio.sleep(1)

                    db.insert_listing(ad)

        except Exception as e:
            print(f"[!] Hata: {e}")

        print(f"[*] Tarama turu bitti. {CHECK_INTERVAL_SECONDS} saniye sonra tekrar edilecek...")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_bot())