import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

BASE = "https://www.arabam.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

MONTHS = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz",
          "ağustos", "eylül", "ekim", "kasım", "aralık"]

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_KM_RE = re.compile(r"^[\d.]+\s*km$", re.I)
_PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:TL|₺)", re.I)


def tr_lower(text: str) -> str:
    """Türkçe harfleri bozmadan küçük harfe çevirir (İ -> i, I -> ı)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def _digits(text: str) -> int:
    d = "".join(ch for ch in text if ch.isdigit())
    return int(d) if d else 0


def build_search_url(keyword: str, page: int = 1) -> str:
    """'Renault Clio 1.5 dCi Joy' -> .../otomobil/renault-clio-1-5-dci-joy?sort=startedAt.desc
    (arabam.com noktaları tire yapıyor; sıralama en yeni ilan önce)."""
    tr_map = str.maketrans("üışçöğÜİIŞÇÖĞ", "uiscogUIISCOG")
    clean = keyword.translate(tr_map).lower()
    clean = re.sub(r"[.\s_/]+", "-", clean.strip())
    clean = re.sub(r"[^a-z0-9-]", "", clean)
    clean = re.sub(r"-{2,}", "-", clean).strip("-")
    url = f"{BASE}/ikinci-el/otomobil/{clean}?sort=startedAt.desc"
    if page > 1:
        url += f"&page={page}"
    return url


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


def _guess_damage_from_title(title: str) -> str:
    t = tr_lower(title)
    if "ağır hasar" in t or "pert" in t:
        return "Ağır Hasarlı"
    if "hatasız" in t or "boyasız" in t:
        return "Hatasız / Boyasız"
    if "değişensiz" in t:
        return "Değişensiz"
    if "hasarlı" in t:
        return "Hasarlı"
    return "Standart"


def parse_listing_row(row):
    """Bir 'tr.listing-list-item' satırını dict'e çevirir. Hücreler sıra numarasına göre değil,
    içeriklerine göre tanınır; site sütun sırasını değiştirse de çalışır."""
    a_tag = row.select_one('a[href^="/ilan/"]')
    if not a_tag:
        return None
    href = a_tag["href"].split("?")[0]
    ad_id = href.rstrip("/").split("/")[-1]
    if not ad_id.isdigit():
        return None

    title_el = row.select_one(".listing-title-lines") or row.select_one("h3")
    model_el = row.select_one("td.listing-modelname")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    model = model_el.get_text(" ", strip=True) if model_el else ""
    if not title:
        title = model

    year = km = price = 0
    location = "Belirtilmemiş"
    for td in row.find_all("td"):
        if td is model_el or (title_el and title_el in td.descendants):
            continue
        # Hücredeki gizli "Karşılaştır / Favoriye ekle" araç kutusunu okumamak için
        # sadece asıl içerik kutusunun metnini al
        content = td.select_one(".fade-out-content-wrapper") or td
        text = content.get_text(" ", strip=True)
        if not text:
            continue
        low = tr_lower(text)
        if not year and _YEAR_RE.match(text):
            year = int(text)
        elif not km and _KM_RE.match(text):
            km = _digits(text)
        elif not price and _PRICE_RE.search(text):
            # İndirimli ilanlarda eski ve yeni fiyat yan yana olabilir: sonuncusu güncel fiyat
            price = _digits(_PRICE_RE.findall(text)[-1])
        elif any(m in low for m in MONTHS) and re.search(r"\d{4}", text):
            continue  # ilan tarihi
        elif price:
            # Fiyattan sonra gelen, tarih olmayan metin hücresi = konum
            location = text

    return {
        "id": ad_id,
        "title": title,
        "model": model,
        "price": price,
        "year": year,
        "km": km,
        "damage_info": _guess_damage_from_title(title),
        "url": BASE + href,
        "location": location,
    }


class ArabamScraper:
    """Tek bir tarayıcıyı açık tutar; her filtrede yeniden Chromium başlatmaz.
    Kullanım: async with ArabamScraper() as s: ..."""

    def __init__(self, headless=True, page_delay=2.5):
        self.headless = headless
        self.page_delay = page_delay
        self._pw = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def start(self):
        if self._pw is None:
            self._pw = await async_playwright().start()
        if self._browser is None or not self._browser.is_connected():
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=USER_AGENT,
                locale="tr-TR",
            )

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
        finally:
            self._browser = self._context = None
            if self._pw:
                await self._pw.stop()
                self._pw = None

    async def _open(self, url: str):
        """Sayfayı açar; tarayıcı çökmüşse bir kez yeniden başlatıp dener."""
        for attempt in range(2):
            try:
                await self.start()
                page = await self._context.new_page()
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    return page, resp
                except Exception:
                    await page.close()
                    raise
            except Exception:
                if attempt == 1:
                    raise
                await self.close()
        raise RuntimeError("unreachable")

    async def fetch_listings(self, keyword: str, pages: int = 1):
        """Filtre anahtar kelimesi için ilk `pages` sayfadaki ilanları (en yeni önce) döner."""
        listings, seen = [], set()
        for page_no in range(1, max(1, pages) + 1):
            url = build_search_url(keyword, page_no)
            try:
                page, resp = await self._open(url)
            except Exception as e:
                print(f"[!] Sayfa açılamadı ({url}): {e}")
                break
            try:
                if resp is not None and resp.status >= 400:
                    print(f"[!] {url} -> HTTP {resp.status}")
                    break
                # arabam.com eşleşme yoksa üst kategoriye yönlendirebilir: bunu yakala
                final = page.url.split("?")[0].rstrip("/")
                wanted = url.split("?")[0].rstrip("/")
                if final != wanted:
                    print(f"[!] Arama adresi yönlendirildi ({wanted} -> {final}). "
                          f"Filtredeki model adını kontrol et.")
                    break
                try:
                    await page.wait_for_selector("tr.listing-list-item", timeout=15000)
                except Exception:
                    break  # bu sayfada ilan yok
                soup = BeautifulSoup(await page.content(), "html.parser")
            finally:
                await page.close()

            rows = soup.select("tr.listing-list-item")
            new_on_page = 0
            for row in rows:
                ad = parse_listing_row(row)
                if ad and ad["id"] not in seen:
                    seen.add(ad["id"])
                    listings.append(ad)
                    new_on_page += 1
            if new_on_page == 0 or len(rows) < 20:
                break  # son sayfa
            await asyncio.sleep(self.page_delay)
        return listings

    async def fetch_details(self, ads: list):
        """Verilen ilanların detay sayfasını açıp gerçek ağır hasar ve
        boya-değişen bilgisini ilana ekler (ad dict'i yerinde güncellenir)."""
        for ad in ads:
            ad["detail_ok"] = False
            ad["removed"] = False
            try:
                page, resp = await self._open(ad["url"])
                try:
                    if resp is not None and resp.status == 404:
                        ad["removed"] = True
                        continue
                    if resp is not None and resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status}")
                    # Satılan / kaldırılan ilan kategori sayfasına yönlendirilir
                    if f"/{ad['id']}" not in page.url:
                        ad["removed"] = True
                        continue
                    try:
                        await page.wait_for_selector("text=Boya-değişen", timeout=10000)
                    except Exception:
                        pass  # satır hiç olmayabilir; yine de metni oku
                    text = await page.inner_text("body")
                finally:
                    await page.close()

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

            await asyncio.sleep(self.page_delay)
