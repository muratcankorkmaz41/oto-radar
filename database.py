import sqlite3
from config import DB_PATH


class Database:
    def __init__(self, db_name=DB_PATH):
        self.db_name = db_name
        self.init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_name, timeout=10)  # bot ve panel aynı anda yazabilir
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql, params=(), fetch=None):
        conn = self._connect()
        try:
            with conn:  # commit / rollback
                cur = conn.execute(sql, params)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
        finally:
            conn.close()

    def init_db(self):
        conn = self._connect()
        try:
            with conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ilanlar (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        price INTEGER NOT NULL,
                        year INTEGER DEFAULT 0,
                        km INTEGER DEFAULT 0,
                        damage_info TEXT DEFAULT 'Standart',
                        url TEXT NOT NULL,
                        location TEXT,
                        is_deal INTEGER DEFAULT 0,
                        avg_price INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Eski veritabanlarına yeni sütunları ekle
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(ilanlar)")}
                if "is_deal" not in cols:
                    conn.execute("ALTER TABLE ilanlar ADD COLUMN is_deal INTEGER DEFAULT 0")
                if "avg_price" not in cols:
                    conn.execute("ALTER TABLE ilanlar ADD COLUMN avg_price INTEGER DEFAULT 0")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS takipler (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        min_year INTEGER DEFAULT 0,
                        max_price INTEGER DEFAULT 0,
                        max_km INTEGER DEFAULT 0,
                        req_boyasiz INTEGER DEFAULT 0,
                        req_degisensiz INTEGER DEFAULT 0,
                        req_hasarsiz INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Hasar filtresine takılan ilanlar: bot yeniden başlasa da tekrar açılmasın
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS elenenler (
                        filter_id INTEGER NOT NULL,
                        ad_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (filter_id, ad_id)
                    )
                """)
        finally:
            conn.close()

    # ---- ilanlar ----
    def is_new_listing(self, ad_id: str) -> bool:
        return self._run("SELECT 1 FROM ilanlar WHERE id = ?", (ad_id,), "one") is None

    def insert_listing(self, ad: dict):
        self._run("""
            INSERT OR IGNORE INTO ilanlar
                (id, title, price, year, km, damage_info, url, location, is_deal, avg_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ad["id"], ad["title"], ad["price"], ad.get("year", 0),
            ad.get("km", 0), ad.get("damage_info", "Standart"),
            ad["url"], ad.get("location", ""),
            1 if ad.get("is_deal") else 0, ad.get("avg_price", 0),
        ))

    def get_recent_listings(self, limit: int = 50):
        return self._run("SELECT * FROM ilanlar ORDER BY created_at DESC, rowid DESC LIMIT ?",
                         (limit,), "all")

    def get_listing_stats(self, recent: int = 20):
        total = self._run("SELECT COUNT(*) AS n FROM ilanlar", (), "one")["n"]
        deals = self._run("SELECT COUNT(*) AS n FROM ilanlar WHERE is_deal = 1", (), "one")["n"]
        row = self._run("""
            SELECT COUNT(*) AS n, AVG(price) AS avg FROM (
                SELECT price FROM ilanlar WHERE price > 0
                ORDER BY created_at DESC, rowid DESC LIMIT ?
            )
        """, (recent,), "one")
        return {"total": total, "deals": deals, "recent_count": row["n"], "avg_price": row["avg"] or 0}

    # ---- filtreler ----
    def add_user_filter(self, keyword: str, min_year: int, max_price: int, max_km: int,
                        req_boyasiz: int, req_degisensiz: int, req_hasarsiz: int):
        self._run("""
            INSERT INTO takipler (keyword, min_year, max_price, max_km, req_boyasiz, req_degisensiz, req_hasarsiz)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (keyword.lower(), min_year, max_price, max_km, req_boyasiz, req_degisensiz, req_hasarsiz))

    def delete_user_filter(self, filter_id: int):
        self._run("DELETE FROM elenenler WHERE filter_id = ?", (filter_id,))
        self._run("DELETE FROM takipler WHERE id = ?", (filter_id,))

    def get_all_filters(self):
        return self._run("SELECT * FROM takipler ORDER BY id DESC", (), "all")

    # ---- elenenler ----
    def is_rejected(self, filter_id: int, ad_id: str) -> bool:
        return self._run("SELECT 1 FROM elenenler WHERE filter_id = ? AND ad_id = ?",
                         (filter_id, ad_id), "one") is not None

    def add_rejected(self, filter_id: int, ad_id: str):
        self._run("INSERT OR IGNORE INTO elenenler (filter_id, ad_id) VALUES (?, ?)",
                  (filter_id, ad_id))
