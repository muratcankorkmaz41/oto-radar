import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def tr_lower(text: str) -> str:
    """Türkçe harfleri bozmadan küçük harfe çevirir (İ -> i, I -> ı)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def parse_damage(text: str):
    """İlan sayfası metninden (ağır hasar, boya-değişen) bilgisini çıkarır.
    Bulunamayan değer None döner."""
    t = tr_lower(text)

    agir = None
    m = re.search(r"ağır hasarlı\s+(evet|hayır|belirtilmemiş)", t)
    if m:
        agir = m.group(1).capitalize()

    boya = None
    m = re.search(
        r"boya-değişen\s+("
        r"(?:\d+\s+(?:lokal boyalı|boyalı|değişen)(?:\s*,\s*)?)+"
        r"|tamamı or(?:i)?jinal"
        r"|belirtilmemiş)",
        t,
    )
    if m:
        boya = m.group(1).strip().rstrip(",")

    # arabam.com, satıcı girmediyse "Ağır Hasarlı" satırını hiç göstermiyor.
    # Sayfa okunmuş (boya satırı var) ama bu satır yoksa "belirtilmemiş" say.
    if agir is None and boya is not None:
        agir = "Belirtilmemiş"

    return agir, boya


def damage_ok(flt, ad, accept_unspecified=False, accept_agir_unspecified=False):
    """Filtredeki switch'lere göre ilanı kontrol eder.
    Döner: (True/False/None, sebep). None = detay okunamadı, sonra tekrar dene."""
    if not ad.get("detail_ok"):
        return None, "detay sayfası okunamadı"

    agir = ad.get("agir_hasarli")
    boya = ad.get("boya_degisen")

    if flt["req_hasarsiz"] == 1:
        if agir == "Evet":
            return False, "ağır hasar kayıtlı"
        if agir is None:
            return False, "'Ağır Hasarlı' satırı sayfada bulunamadı"
        if agir == "Belirtilmemiş" and not accept_agir_unspecified:
            return False, "ağır hasar: belirtilmemiş"

    if flt["req_boyasiz"] == 1:
        if boya is None or boya == "belirtilmemiş":
            if not accept_unspecified:
                return False, "'Boya-değişen' satırı yok" if boya is None else "boya-değişen: belirtilmemiş"
        elif "boyalı" in boya:
            return False, f"boyalı parça var ({boya})"

    if flt["req_degisensiz"] == 1:
        if boya is None or boya == "belirtilmemiş":
            if not accept_unspecified:
                return False, "'Boya-değişen' satırı yok" if boya is None else "boya-değişen: belirtilmemiş"
        elif "değişen" in boya:
            return False, f"değişen parça var ({boya})"

    return True, ""


class ArabamScraper:
    def __init__(self, headless=True):
        self.headless = headless

    async def _launch(self, p):
        browser = await p.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=USER_AGENT
        )
        return browser, context

    async def fetch_listings(self, target_url: str):
        listings = []

        async with async_playwright() as p:
            browser, context = await self._launch(p)
            page = await context.new_page()

            try:
                # Timeout'u 60 saniyeye çıkarıp tıkanıklığı önlüyoruz
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)  # Sitenin tam yüklenmesi için bekleme

                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                rows = soup.select("tr.listing-list-item")

                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 7:
                        continue

                    a_tag = cells[2].find("a") or cells[1].find("a")
                    if not a_tag or not a_tag.has_attr("href"):
                        continue

                    href = a_tag["href"]
                    if not href.startswith("/ilan/"):
                        continue

                    ad_id = href.rstrip("/").split("/")[-1]
                    url = "https://www.arabam.com" + href

                    title = cells[2].get_text(" ", strip=True)
                    if not title:
                        title = cells[1].get_text(" ", strip=True)

                    year_text = "".join(filter(str.isdigit, cells[3].get_text()))
                    year = int(year_text) if year_text else 0

                    km_text = "".join(filter(str.isdigit, cells[4].get_text()))
                    km = int(km_text) if km_text else 0

                    price_text = "".join(filter(str.isdigit, cells[6].get_text()))
                    price = int(price_text) if price_text else 0

                    location = "Belirtilmemiş"
                    if len(cells) > 8:
                        location = cells[8].get_text(" ", strip=True).replace("Karşılaştır", "").strip()
                    elif len(cells) > 7:
                        loc_temp = cells[7].get_text(" ", strip=True)
                        months = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]
                        if not any(m in loc_temp.lower() for m in months):
                            location = loc_temp.replace("Karşılaştır", "").strip()

                    # Başlıktan tahmini hasar bilgisi (detay sayfası okunursa üzerine yazılır)
                    damage_info = "Standart"
                    t_lower = tr_lower(title)
                    if "ağır hasar" in t_lower or "pert" in t_lower:
                        damage_info = "Ağır Hasarlı"
                    elif "hatasız" in t_lower or "boyasız" in t_lower:
                        damage_info = "Hatasız / Boyasız"
                    elif "değişensiz" in t_lower:
                        damage_info = "Değişensiz"
                    elif "hasarlı" in t_lower:
                        damage_info = "Hasarlı"

                    listings.append({
                        "id": str(ad_id),
                        "title": title,
                        "price": price,
                        "year": year,
                        "km": km,
                        "damage_info": damage_info,
                        "url": url,
                        "location": location
                    })

            except Exception as e:
                print(f"[!] Tarayıcı Sayfayı Çekemedi (Timeout veya Engelleme): {e}")
            finally:
                await browser.close()

        return listings

    async def fetch_details(self, ads: list):
        """Verilen ilanların detay sayfasını açıp gerçek ağır hasar ve
        boya-değişen bilgisini ilana ekler (ad dict'i yerinde güncellenir)."""
        if not ads:
            return

        async with async_playwright() as p:
            browser, context = await self._launch(p)
            page = await context.new_page()

            try:
                for ad in ads:
                    ad["detail_ok"] = False
                    try:
                        await page.goto(ad["url"], wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(3)
                        text = await page.inner_text("body")

                        agir, boya = parse_damage(text)
                        ad["agir_hasarli"] = agir
                        ad["boya_degisen"] = boya
                        ad["detail_ok"] = True

                        if agir or boya:
                            parts = []
                            if agir:
                                parts.append(f"Ağır hasar: {agir}")
                            if boya:
                                parts.append(f"Boya-değişen: {boya[:1].upper() + boya[1:]}")
                            ad["damage_info"] = " | ".join(parts)
                    except Exception as e:
                        print(f"[!] Detay sayfası okunamadı ({ad['id']}): {e}")

                    await asyncio.sleep(2)
            finally:
                await browser.close()