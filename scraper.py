import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class ArabamScraper:
    def __init__(self, headless=True):
        self.headless = headless

    async def fetch_listings(self, target_url: str):
        listings = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                # Timeout'u 60 saniyeye çıkarıp tıkanıklığı önlüyoruz
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3) # Sitenin tam yüklenmesi için bekleme süresini biraz artırdık
                
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

                    damage_info = "Standart"
                    t_lower = title.lower()
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