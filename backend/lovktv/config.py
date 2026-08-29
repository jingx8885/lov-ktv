import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("LOVKTV_DATA", ROOT / "data")).resolve()
MEDIA_DIR = (DATA_DIR / "media").resolve()
MODELS_DIR = Path(os.environ.get("LOVKTV_MODELS", DATA_DIR / "models")).resolve()
WHISPER_DIR = Path(
    os.environ.get("LOVKTV_WHISPER_DIR", Path.home() / ".cache" / "whisper")
).resolve()
IMAGE_MODELS_DIR = Path("/opt/lovktv/models")
DB_PATH = DATA_DIR / "lovktv.sqlite"
# postgres/postgresql URL → PostgreSQL (Supabase). Empty → SQLite at DB_PATH.
DATABASE_URL = (
    os.environ.get("LOVKTV_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
).strip()
HOST = "0.0.0.0"
PORT = 8787
PUBLIC_URL = (os.environ.get("LOVKTV_PUBLIC_URL") or "").rstrip("/")
WECHAT_APP_ID = (
    os.environ.get("WECHAT_APP_ID") or os.environ.get("LOVKTV_WECHAT_APP_ID") or ""
)
WECHAT_APP_SECRET = (
    os.environ.get("WECHAT_APP_SECRET")
    or os.environ.get("LOVKTV_WECHAT_APP_SECRET")
    or ""
)
WECHAT_MP_APP_ID = os.environ.get("WECHAT_MP_APP_ID") or WECHAT_APP_ID
WECHAT_MP_APP_SECRET = os.environ.get("WECHAT_MP_APP_SECRET") or WECHAT_APP_SECRET
SESSION_DAYS = 30
QR_TTL_MS = 180_000
ALIYUN_OSS_ENABLED = (os.environ.get("ALIYUN_OSS_ENABLED") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ALIYUN_OSS_ACCESS_KEY_ID = os.environ.get("ALIYUN_OSS_ACCESS_KEY_ID") or ""
ALIYUN_OSS_ACCESS_KEY_SECRET = os.environ.get("ALIYUN_OSS_ACCESS_KEY_SECRET") or ""
ALIYUN_OSS_ENDPOINT = (os.environ.get("ALIYUN_OSS_ENDPOINT") or "").strip()
ALIYUN_OSS_BUCKET_NAME = (os.environ.get("ALIYUN_OSS_BUCKET_NAME") or "").strip()
ALIYUN_OSS_BASE_PATH = (
    os.environ.get("LOVKTV_OSS_PREFIX")
    or os.environ.get("ALIYUN_OSS_BASE_PATH")
    or "lovktv"
).strip() or "lovktv"
ALIYUN_OSS_DOWNLOAD_DOMAIN = (
    os.environ.get("ALIYUN_OSS_DOWNLOAD_DOMAIN") or ""
).rstrip("/")
HTTPS_PROXY = (os.environ.get("LOVKTV_HTTPS_PROXY") or "").strip()
