from telegram import Bot

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.bot = Bot(token=token) if token != "BURAYA_BOT_TOKEN_YAZILACAK" else None

    async def send_listing_alert(self, ad: dict):
        if not self.bot:
            return

        year_text = f"{ad['year']} Model" if ad.get("year") else "Yıl Belirtilmemiş"
        km_text = f"{ad['km']:,} KM".replace(",", ".") if ad.get("km") else "KM Belirtilmemiş"
        damage_tag = ad.get("damage_info", "Standart")
        
        # Hasar durumuna göre rozet
        badge = "🚗 Radar Eşleşti!"
        if "Ağır" in damage_tag:
            badge = "⚠️ Ağır Hasarlı Araç"
        elif "Hatasız" in damage_tag or "Boyasız" in damage_tag:
            badge = "💎 Hatasız / Boyasız"

        mesaj = (
            f"<b>{badge}</b>\n\n"
            f"📌 <b>İlan:</b> {ad['title']}\n"
            f"📅 <b>Yıl:</b> {year_text}\n"
            f"🛣️ <b>Kilometre:</b> {km_text}\n"
            f"🛠️ <b>Hasar Durumu:</b> {damage_tag}\n"
            f"💰 <b>Fiyat:</b> {ad['price']:,} TL\n".replace(",", ".") +
            f"📍 <b>Konum:</b> {ad.get('location', 'Belirtilmemiş')}\n\n"
            f"🔗 <a href='{ad['url']}'>İlana Git</a>"
        )

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=mesaj,
                parse_mode="HTML"
            )
            print(f"[Bildirim Gönderildi] {ad['title']}")
        except Exception as e:
            print(f"[Bildirim Hatası]: {e}")