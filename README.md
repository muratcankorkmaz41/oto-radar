# Oto Fiyat Botu

arabam.com'daki yeni ikinci el otomobil ilanlarını senin filtrelerine göre takip eder,
uygun ilan düşünce Telegram'a haber verir. Aynı aramadaki ortalamadan belirgin ucuz
ilanları **🔥 Fırsat** olarak işaretler.

## Kurulum

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

`.env.example` dosyasını `.env` adıyla kopyala, Telegram bilgilerini yaz:

- `TELEGRAM_BOT_TOKEN`: BotFather'dan alınan token
- `TELEGRAM_CHAT_ID`: @userinfobot'tan alınan sayısal ID

`.env` gizlidir. Kimseyle paylaşma (git'e eklenmez).

## Çalıştırma

İki ayrı terminalde:

```bash
python app.py     # Panel: http://127.0.0.1:5000  (filtre ekle / sil)
python main.py    # Bot: filtreleri tarar ve bildirim gönderir
```

## Nasıl çalışır

1. Her filtre için arabam.com araması **en yeni ilan önce** sıralanarak açılır,
   `PAGES_PER_FILTER` kadar sayfa okunur (sayfa başı 20 ilan).
2. Daha önce bildirilen ilanlar, fiyat / km / yıl sınırını aşanlar elenir.
3. Boyasız / Değişensiz / Ağır hasarsız seçiliyse ilanın detay sayfası açılıp gerçek
   bilgi okunur. Bu kontrolden elenen ilanlar veritabanında tutulur, tekrar açılmaz.
4. Ortalama fiyattan `DEAL_DISCOUNT_THRESHOLD` (varsayılan %10) kadar ucuz ilanlar fırsattır.
5. Telegram mesajı gittiyse ilan kaydedilir. Gitmediyse sonraki turda tekrar denenir.

## Ayarlar (`.env`)

| Ayar | Varsayılan | Açıklama |
|---|---|---|
| `CHECK_INTERVAL_SECONDS` | 300 | İki tarama turu arası bekleme |
| `PAGES_PER_FILTER` | 2 | Filtre başına okunacak sonuç sayfası |
| `MAX_DETAIL_PER_ROUND` | 15 | Turda en fazla açılacak detay sayfası |
| `DEAL_DISCOUNT_THRESHOLD` | 0.10 | Fırsat eşiği (0.10 = %10) |
| `FLASK_DEBUG` | 0 | 1 yaparsan panel debug modunda açılır (ağa açma!) |

Siteyi yormamak için sayfalar arasında birkaç saniye beklenir. Tarama aralığını çok düşürme.
