-- lov-ktv · PostgreSQL / Supabase
-- 粘贴到 Supabase SQL Editor 执行。时间戳是纪元毫秒，必须用 BIGINT。
-- 由 lovktv.core.schema.POSTGRES_DDL 生成，不要手改；
-- backend/tests/test_schema.py 会比对两边是否一致。

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
  display_mode TEXT NOT NULL DEFAULT 'mv',
  now_index INTEGER NOT NULL DEFAULT 0,
  paused INTEGER NOT NULL DEFAULT 0,
  lan_origin TEXT NOT NULL DEFAULT '',
  lan_mic_port INTEGER NOT NULL DEFAULT 0,
  lan_mic_sample_rate INTEGER NOT NULL DEFAULT 48000,
  lan_seen_at BIGINT NOT NULL DEFAULT 0
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
CREATE TABLE IF NOT EXISTS song_favorites (
  owner TEXT NOT NULL,
  song_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (owner, song_id)
);
CREATE INDEX IF NOT EXISTS song_favorites_song ON song_favorites (song_id);
CREATE INDEX IF NOT EXISTS users_wechat ON users (wechat_openid);
CREATE INDEX IF NOT EXISTS users_device ON users (device_id);
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
CREATE TABLE IF NOT EXISTS learn_progress (
  owner TEXT NOT NULL, song_id TEXT NOT NULL, unit_id TEXT NOT NULL, skill TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready', score INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0, updated_at BIGINT NOT NULL,
  PRIMARY KEY (owner, song_id, unit_id, skill)
);
CREATE TABLE IF NOT EXISTS learn_mastery (
  owner TEXT NOT NULL, song_id TEXT NOT NULL, kind TEXT NOT NULL, item_key TEXT NOT NULL,
  text TEXT NOT NULL DEFAULT '', zh TEXT NOT NULL DEFAULT '', correct INTEGER NOT NULL DEFAULT 0,
  wrong INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0, mastered INTEGER NOT NULL DEFAULT 0,
  updated_at BIGINT NOT NULL, PRIMARY KEY (owner, song_id, kind, item_key)
);
CREATE TABLE IF NOT EXISTS learn_mistakes (
  owner TEXT NOT NULL, song_id TEXT NOT NULL, qkind TEXT NOT NULL, item_key TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '', stem TEXT NOT NULL DEFAULT '', answer_text TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL DEFAULT '', wrong_count INTEGER NOT NULL DEFAULT 0,
  correct_streak INTEGER NOT NULL DEFAULT 0, last_wrong_at BIGINT NOT NULL DEFAULT 0,
  resolved_at BIGINT NOT NULL DEFAULT 0,
  stage INTEGER NOT NULL DEFAULT 0, reps INTEGER NOT NULL DEFAULT 0,
  lapses INTEGER NOT NULL DEFAULT 0, due_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (owner, song_id, qkind, item_key)
);
CREATE TABLE IF NOT EXISTS learn_submissions (
  owner TEXT NOT NULL, song_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (owner, song_id, attempt_id)
);
CREATE TABLE IF NOT EXISTS learn_cards (
  owner TEXT NOT NULL, card_id TEXT NOT NULL, song_id TEXT NOT NULL DEFAULT '',
  song_title TEXT NOT NULL DEFAULT '', item_key TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '', zh TEXT NOT NULL DEFAULT '', romaji TEXT NOT NULL DEFAULT '',
  line_text TEXT NOT NULL DEFAULT '', start_ms BIGINT NOT NULL DEFAULT 0,
  end_ms BIGINT NOT NULL DEFAULT 0, stage INTEGER NOT NULL DEFAULT 0,
  reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
  due_at BIGINT NOT NULL DEFAULT 0, last_at BIGINT NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL DEFAULT 0, retired_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (owner, card_id)
);
CREATE INDEX IF NOT EXISTS learn_cards_due ON learn_cards (owner, retired_at, due_at);
CREATE TABLE IF NOT EXISTS learn_recite_days (
  owner TEXT NOT NULL, deck TEXT NOT NULL, day TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (owner, deck, day)
);
CREATE TABLE IF NOT EXISTS learn_words (
  owner TEXT NOT NULL, word_id TEXT NOT NULL, language TEXT NOT NULL DEFAULT '',
  norm TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '',
  zh TEXT NOT NULL DEFAULT '', romaji TEXT NOT NULL DEFAULT '',
  stage INTEGER NOT NULL DEFAULT 0, reps INTEGER NOT NULL DEFAULT 0,
  lapses INTEGER NOT NULL DEFAULT 0, due_at BIGINT NOT NULL DEFAULT 0,
  last_at BIGINT NOT NULL DEFAULT 0, created_at BIGINT NOT NULL DEFAULT 0,
  retired_at BIGINT NOT NULL DEFAULT 0, skipped_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (owner, word_id)
);
CREATE INDEX IF NOT EXISTS learn_words_due ON learn_words (owner, skipped_at, retired_at, due_at);
CREATE TABLE IF NOT EXISTS learn_word_sources (
  owner TEXT NOT NULL, word_id TEXT NOT NULL, song_id TEXT NOT NULL,
  song_title TEXT NOT NULL DEFAULT '', line_text TEXT NOT NULL DEFAULT '',
  start_ms BIGINT NOT NULL DEFAULT 0, end_ms BIGINT NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (owner, word_id, song_id)
);
CREATE INDEX IF NOT EXISTS learn_word_sources_song ON learn_word_sources (owner, song_id);
CREATE TABLE IF NOT EXISTS learn_migrations (
  owner TEXT NOT NULL, kind TEXT NOT NULL, created_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (owner, kind)
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at BIGINT NOT NULL
);
