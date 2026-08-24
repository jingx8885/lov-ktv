import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("LOVKTV_DATA", ROOT / "data")).resolve()
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "lovktv.sqlite"
HOST = "0.0.0.0"
PORT = 8787
PUBLIC_URL = (os.environ.get("LOVKTV_PUBLIC_URL") or "").rstrip("/")
WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID") or os.environ.get("LOVKTV_WECHAT_APP_ID") or ""
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET") or os.environ.get("LOVKTV_WECHAT_APP_SECRET") or ""
WECHAT_MP_APP_ID = os.environ.get("WECHAT_MP_APP_ID") or WECHAT_APP_ID
WECHAT_MP_APP_SECRET = os.environ.get("WECHAT_MP_APP_SECRET") or WECHAT_APP_SECRET
SESSION_DAYS = 30
QR_TTL_MS = 180_000
