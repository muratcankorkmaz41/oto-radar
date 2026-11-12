import asyncio
import html
from telegram import Bot


def _tl(value: int) -> str:
    """1375000 -> 1.375.000"""
    return f"{value:,}".replace(",", ".")


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, max_tries: int = 3, retry_delay: float = 3):
        self.chat_id = chat_id
        self.max_tries = max_tries
        self.retry_delay = retry_delay
        self.enabled = bool(token and chat_id)
        self.bot = Bot(token=token) if self.enabled else None

    def _badge(self, ad: dict) -> str:
        agir = ad.get("agir_hasarli")
        boya = ad.get("boya_degisen") or ""

        # Detay sayfası okunduysa gerçek bilgiye göre rozet
        if agir is not None or boya:
            if agir == "Evet":
                return "\U000026a0\U0000fe0f Ağır Hasarlı Araç"
            if agir == "Hayır" and boya.startswith("tamamı"):
                return "\U0001f48e Hatasız / Boyasız"
            return "\U0001f697 Radar Eşleşti!"

        # Detay yoksa başlıktan tahmin edilen bilgiye göre
        damage_tag = ad.get("damage_info") or "Standart"
        if "Ağır" in damage_tag:
            return "\U000026a0\U0000fe0f Ağır Hasarlı Araç"
        if "Hatasız" in damage_tag or "Boyasız" in damage_tag:
            return "\U0001f48e Hatasız / Boyasız"
        return "\U0001f697 Radar Eşleşti!"

    def build_message(self, ad: dict) -> str:
        year_text = f"{ad['year']} Model" if ad.get("year") else "Yıl Belirtilmemiş"
        km_text = f"{_tl(ad['km'])} KM" if ad.get("km") else "KM Belirtilmemiş"
        damage_tag = ad.get("damage_info") or "Standart"

        deal_line = ""
        if ad.get("is_deal"):
            deal_line = (f"\U0001f525 <b>FIRSAT:</b> bu aramadaki ortalamadan %{ad.get('discount_pct', 0)} ucuz "
                         f"(ort. {_tl(ad.get('avg_price', 0))} TL)\n\n")

        return (
            f"<b>{self._badge(ad)}</b>\n\n"
            f"{deal_line}"
            f"\U0001f4cc <b>İlan:</b> {html.escape(ad['title'])}\n"
            f"\U0001f4c5 <b>Yıl:</b> {year_text}\n"
            f"\U0001f6e3\U0000fe0f <b>Kilometre:</b> {km_text}\n"
            f"\U0001f6e0\U0000fe0f <b>Hasar Durumu:</b> {html.escape(damage_tag)}\n"
            f"\U0001f4b0 <b>Fiyat:</b> {_tl(ad['price'])} TL\n"
            f"\U0001f4cd <b>Konum:</b> {html.escape(ad.get('location') or 'Belirtilmemiş')}\n\n"
            f"\U0001f517 <a href=\"{html.escape(ad['url'], quote=True)}\">İlana Git</a>"
        )

    async def send_listing_alert(self, ad: dict) -> bool:
        """Mesaj gitti ise True, gitmediyse False döner."""
        if not self.enabled:
            return True  # Token girilmemiş, bildirim kapalı sayılır

        mesaj = self.build_message(ad)
        for deneme in range(1, self.max_tries + 1):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=mesaj,
                    parse_mode="HTML",
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                )
                print(f"[Bildirim Gönderildi] {ad['title']}")
                return True
            except Exception as e:
                print(f"[Bildirim Hatası] ({deneme}/{self.max_tries}): {e}")
                if deneme < self.max_tries:
                    await asyncio.sleep(self.retry_delay)

        print("[!] Bildirim gönderilemedi, ilan kaydedilmedi, sonraki turda tekrar denenecek.")
        return False
