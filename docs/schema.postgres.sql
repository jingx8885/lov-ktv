-- lov-ktv · PostgreSQL / Supabase
-- 粘贴到 Supabase SQL Editor 执行。时间戳是纪元毫秒，必须用 BIGINT。

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
  username TEXT NOT NULL DEFAULT '',
  username_key TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL DEFAULT '',
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
CREATE UNIQUE INDEX IF NOT EXISTS users_username_key ON users (username_key) WHERE username_key <> '';
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS login_tickets_exp ON login_tickets (expires_at);

CREATE TABLE IF NOT EXISTS hosts (
  key TEXT PRIMARY KEY,
  room TEXT NOT NULL,
  ua TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL,
  last_seen BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS hosts_room ON hosts (room);

CREATE TABLE IF NOT EXISTS guest_song_counts (
  guest_key TEXT NOT NULL,
  day TEXT NOT NULL,
  used INTEGER NOT NULL,
  PRIMARY KEY (guest_key, day)
);

CREATE TABLE IF NOT EXISTS point_wallets (
  owner TEXT PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS point_ledger (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  kind TEXT NOT NULL,
  delta INTEGER NOT NULL,
  ref TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS point_ledger_owner ON point_ledger (owner, created_at);
CREATE TABLE IF NOT EXISTS ad_sessions (
  token TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  placement TEXT NOT NULL,
  ad_id TEXT NOT NULL,
  started_at BIGINT NOT NULL,
  completed_at BIGINT NOT NULL DEFAULT 0,
  clicked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS point_claims (
  owner TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (owner, kind)
);
