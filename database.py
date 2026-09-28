import sqlite3

class Database:
    def __init__(self, db_name="ilanlar.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ilanlar (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    year INTEGER DEFAULT 0,
                    km INTEGER DEFAULT 0,
                    damage_info TEXT DEFAULT 'Standart',
                    url TEXT NOT NULL,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
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
            conn.commit()

    def is_new_listing(self, ad_id: str) -> bool:
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM ilanlar WHERE id = ?", (ad_id,))
            return cursor.fetchone() is None

    def insert_listing(self, ad: dict):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO ilanlar (id, title, price, year, km, damage_info, url, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ad["id"], ad["title"], ad["price"], ad.get("year", 0),
                ad.get("km", 0), ad.get("damage_info", "Standart"), 
                ad["url"], ad.get("location", "")
            ))
            conn.commit()

    def add_user_filter(self, keyword: str, min_year: int, max_price: int, max_km: int, req_boyasiz: int, req_degisensiz: int, req_hasarsiz: int):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO takipler (keyword, min_year, max_price, max_km, req_boyasiz, req_degisensiz, req_hasarsiz)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (keyword.lower(), min_year, max_price, max_km, req_boyasiz, req_degisensiz, req_hasarsiz))
            conn.commit()

    def delete_user_filter(self, filter_id: int):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM takipler WHERE id = ?", (filter_id,))
            conn.commit()

    def get_all_filters(self):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM takipler ORDER BY id DESC")
            return cursor.fetchall()

    def get_all_listings(self):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ilanlar ORDER BY created_at DESC")
            return cursor.fetchall()