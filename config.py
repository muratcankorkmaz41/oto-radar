"""Ayarlar. Gizli bilgiler (token vb.) koda değil, proje klasöründeki .env dosyasına yazılır.
Örnek için .env.example dosyasına bak."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path):
    """Basit .env okuyucu: ANAHTAR=değer satırları. Gerçek ortam değişkenleri önceliklidir."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env_file(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

CHECK_INTERVAL_SECONDS = _int("CHECK_INTERVAL_SECONDS", 300)   # 5 dakikada bir kontrol
DEAL_DISCOUNT_THRESHOLD = _float("DEAL_DISCOUNT_THRESHOLD", 0.10)  # ortalamadan %10+ ucuzsa "fırsat"
PAGES_PER_FILTER = _int("PAGES_PER_FILTER", 2)                 # her filtre için taranacak sayfa (20 ilan/sayfa)
MAX_DETAIL_PER_ROUND = _int("MAX_DETAIL_PER_ROUND", 15)        # turda en fazla açılacak detay sayfası

DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "ilanlar.db"))

FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "")
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
