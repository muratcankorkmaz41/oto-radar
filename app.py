from flask import Flask, render_template, request, redirect
from database import Database

app = Flask(__name__)
db = Database()


@app.route("/")
def index():
    listings = db.get_all_listings()
    user_filters = db.get_all_filters()

    recent_listings = listings[:20] if listings else []
    avg_price = 0
    if recent_listings:
        valid_prices = [ad["price"] for ad in recent_listings if ad["price"] > 0]
        if valid_prices:
            avg_price = sum(valid_prices) / len(valid_prices)

    return render_template(
        "index.html",
        listings=listings,
        filters=user_filters,
        avg_price=avg_price,
        recent_count=len(recent_listings),
        total_count=len(listings)
    )


@app.route("/add_filter", methods=["POST"])
def add_filter():
    keyword = request.form.get("keyword", "").strip()
    min_year = int(request.form.get("min_year") or 0)
    max_price = int(request.form.get("max_price") or 0)
    max_km = int(request.form.get("max_km") or 0)

    # Switch verilerini 1 veya 0 olarak al
    req_boyasiz = 1 if request.form.get("req_boyasiz") else 0
    req_degisensiz = 1 if request.form.get("req_degisensiz") else 0
    req_hasarsiz = 1 if request.form.get("req_hasarsiz") else 0

    if keyword:
        db.add_user_filter(keyword, min_year, max_price, max_km, req_boyasiz, req_degisensiz, req_hasarsiz)

    return redirect("/")


@app.route("/delete_filter/<int:filter_id>", methods=["POST"])
def delete_filter(filter_id):
    db.delete_user_filter(filter_id)
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True, port=5000)