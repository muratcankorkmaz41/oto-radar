import hmac
import secrets
from flask import Flask, render_template, request, redirect, session, abort, flash
from database import Database
from config import FLASK_SECRET_KEY, FLASK_DEBUG

app = Flask(__name__)
# .env'de yoksa her açılışta rastgele anahtar (sadece oturumlar sıfırlanır)
app.secret_key = FLASK_SECRET_KEY or secrets.token_hex(32)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # index.html değişince panel yeniden başlatılmadan güncellensin
db = Database()


# ---- Basit CSRF koruması: her POST formunda oturuma bağlı gizli bir token olmalı ----
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Geçersiz form gönderimi (CSRF). Sayfayı yenileyip tekrar dene.")


def form_int(name: str, low: int, high: int) -> int:
    """Formdan güvenli tam sayı okur; boş/yanlış değer 0, sınır dışı değer hata."""
    raw = "".join(ch for ch in request.form.get(name, "") if ch.isdigit())
    if not raw:
        return 0
    value = int(raw)
    if not (low <= value <= high):
        raise ValueError(name)
    return value


LISTING_FIELDS = ("id", "title", "price", "year", "km", "damage_info", "url",
                  "location", "is_deal", "avg_price", "created_at")


def listings_payload(limit: int = 300):
    """İlanları sayfanın JavaScript'inin kullanacağı sade sözlüklere çevirir."""
    return [{k: row[k] for k in LISTING_FIELDS} for row in db.get_recent_listings(limit)]


@app.route("/")
def index():
    stats = db.get_listing_stats(recent=20)
    return render_template(
        "index.html",
        listings=listings_payload(),
        filters=db.get_all_filters(),
        avg_price=stats["avg_price"],
        recent_count=stats["recent_count"],
        total_count=stats["total"],
        deal_count=stats["deals"],
    )


@app.route("/api/listings")
def api_listings():
    """Sayfa her dakika buradan yeni ilanları çeker (yenilemeden güncellenir)."""
    stats = db.get_listing_stats(recent=20)
    return {"listings": listings_payload(), "stats": stats}


@app.route("/add_filter", methods=["POST"])
def add_filter():
    keyword = request.form.get("keyword", "").strip()[:120]
    try:
        min_year = form_int("min_year", 1950, 2100)
        max_price = form_int("max_price", 1, 1_000_000_000)
        max_km = form_int("max_km", 1, 5_000_000)
    except ValueError as e:
        names = {"min_year": "model yılı", "max_price": "fiyat", "max_km": "kilometre"}
        flash(f"Geçersiz {names.get(str(e), 'değer')} girdin, filtre eklenmedi.")
        return redirect("/")

    # Switch verilerini 1 veya 0 olarak al
    req_boyasiz = 1 if request.form.get("req_boyasiz") else 0
    req_degisensiz = 1 if request.form.get("req_degisensiz") else 0
    req_hasarsiz = 1 if request.form.get("req_hasarsiz") else 0

    if keyword:
        db.add_user_filter(keyword, min_year, max_price, max_km, req_boyasiz, req_degisensiz, req_hasarsiz)
    else:
        flash("Önce en az bir marka seç.")

    return redirect("/")


@app.route("/delete_filter/<int:filter_id>", methods=["POST"])
def delete_filter(filter_id):
    db.delete_user_filter(filter_id)
    return redirect("/")


if __name__ == "__main__":
    # Sadece bu bilgisayardan erişilir. Debug modu .env'de FLASK_DEBUG=1 ile açılır
    # (debug açıkken paneli asla ağa açma: uzaktan kod çalıştırmaya izin verir).
    app.run(host="127.0.0.1", port=5000, debug=FLASK_DEBUG)
