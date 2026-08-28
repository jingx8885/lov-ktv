"""Canonical tables. Postgres is the production dialect; SQLite is for local tests."""

from __future__ import annotations

TABLES: dict[str, tuple[str, ...]] = {
    "songs": (
        "id",
        "title",
        "artist",
        "language",
        "status",
        "error",
        "audio_source",
        "netease_id",
        "created_at",
    ),
    "rooms": (
        "code",
        "created_at",
        "vocal_mix",
        "volume",
        "mic_gain",
        "lyric_mode",
        "now_index",
    ),
    "queue": ("id", "room", "song_id", "position", "created_at"),
    "users": (
        "id",
        "wechat_openid",
        "wechat_unionid",
        "device_id",
        "nickname",
        "avatar",
        "created_at",
    ),
    "sessions": ("token", "user_id", "created_at", "expires_at"),
    "login_tickets": ("id", "status", "user_id", "created_at", "expires_at"),
}

SONG_FIELDS = frozenset(TABLES["songs"]) - {"id", "created_at"}
ROOM_FIELDS = frozenset({"vocal_mix", "volume", "mic_gain", "lyric_mode", "now_index"})

# Epoch milliseconds overflow 32-bit INTEGER on Postgres.
SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS songs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  artist TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT 'zh',
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT NOT NULL DEFAULT '',
  audio_source TEXT NOT NULL DEFAULT '',
  netease_id TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
  code TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  vocal_mix REAL NOT NULL DEFAULT 1,
  volume INTEGER NOT NULL DEFAULT 80,
  mic_gain INTEGER NOT NULL DEFAULT 80,
  lyric_mode TEXT NOT NULL DEFAULT 'all',
  now_index INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS queue (
  id TEXT PRIMARY KEY,
  room TEXT NOT NULL,
  song_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  wechat_openid TEXT NOT NULL DEFAULT '',
  wechat_unionid TEXT NOT NULL DEFAULT '',
  device_id TEXT NOT NULL DEFAULT '',
  nickname TEXT NOT NULL DEFAULT '',
  avatar TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_tickets (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS queue_room_pos ON queue (room, position);
CREATE INDEX IF NOT EXISTS queue_song ON queue (song_id);
CREATE INDEX IF NOT EXISTS users_wechat ON users (wechat_openid);
CREATE INDEX IF NOT EXISTS users_device ON users (device_id);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS login_tickets_exp ON login_tickets (expires_at);
"""

POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS songs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  artist TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT 'zh',
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT NOT NULL DEFAULT '',
  audio_source TEXT NOT NULL DEFAULT '',
  netease_id TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
  code TEXT PRIMARY KEY,
  created_at BIGINT NOT NULL,
  vocal_mix DOUBLE PRECISION NOT NULL DEFAULT 1,
  volume INTEGER NOT NULL DEFAULT 80,
  mic_gain INTEGER NOT NULL DEFAULT 80,
  lyric_mode TEXT NOT NULL DEFAULT 'all',
  now_index INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS queue (
  id TEXT PRIMARY KEY,
  room TEXT NOT NULL,
  song_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  wechat_openid TEXT NOT NULL DEFAULT '',
  wechat_unionid TEXT NOT NULL DEFAULT '',
  device_id TEXT NOT NULL DEFAULT '',
  nickname TEXT NOT NULL DEFAULT '',
  avatar TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_tickets (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS queue_room_pos ON queue (room, position);
CREATE INDEX IF NOT EXISTS queue_song ON queue (song_id);
CREATE INDEX IF NOT EXISTS users_wechat ON users (wechat_openid);
CREATE INDEX IF NOT EXISTS users_device ON users (device_id);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS login_tickets_exp ON login_tickets (expires_at);
"""

ROOM_MIGRATIONS = (
    ("mic_gain", "INTEGER NOT NULL DEFAULT 80"),
    ("lyric_mode", "TEXT NOT NULL DEFAULT 'all'"),
)
