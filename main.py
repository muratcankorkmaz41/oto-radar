import asyncio
import re
from scraper import ArabamScraper
from database import Database
from notifier import TelegramNotifier
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CHECK_INTERVAL_SECONDS

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
                
                for ad in listings:
                    if db.is_new_listing(ad["id"]):
                        if flt["max_price"] > 0 and ad["price"] > flt["max_price"]: continue
                        if flt["max_km"] > 0 and ad["km"] > 0 and ad["km"] > flt["max_km"]: continue
                        if flt["min_year"] > 0 and ad["year"] > 0 and ad["year"] < flt["min_year"]: continue
                            
                        ad_damage = ad.get("damage_info", "").lower()
                        
                        if flt["req_hasarsiz"] == 1 and "ağır" in ad_damage:
                            continue
                            
                        if flt["req_boyasiz"] == 1 and "boyasız" not in ad_damage and "hatasız" not in ad_damage:
                            continue
                            
                        if flt["req_degisensiz"] == 1 and "değişensiz" not in ad_damage and "hatasız" not in ad_damage:
                            continue

                        print(f"[UYGUN ARAÇ BULUNDU] {ad['title']} - {ad['year']} Model - {ad['km']:,} KM")
                        await notifier.send_listing_alert(ad)
                        await asyncio.sleep(1)
                        
                        db.insert_listing(ad)
                        
        except Exception as e:
            print(f"[!] Hata: {e}")
            
        print(f"[*] Tarama turu bitti. {CHECK_INTERVAL_SECONDS} saniye sonra tekrar edilecek...")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(run_bot())