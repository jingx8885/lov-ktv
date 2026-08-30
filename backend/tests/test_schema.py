from lovktv.core.db import adapt_sql, dialect, is_postgres_url, table_columns
from lovktv.core.schema import POSTGRES_DDL, SQLITE_DDL, TABLES


def test_schema_covers_current_tables():
    assert set(TABLES) == {
        "songs",
        "rooms",
        "queue",
        "users",
        "sessions",
        "login_tickets",
        "hosts",
        "guest_song_counts",
        "point_wallets",
        "point_ledger",
        "ad_sessions",
        "point_claims",
        "learn_progress",
        "learn_mastery",
        "learn_mistakes",
    }
    assert TABLES["songs"] == (
        "id",
        "title",
        "artist",
        "language",
        "status",
        "error",
        "audio_source",
        "netease_id",
        "created_at",
    )
    assert TABLES["rooms"] == (
        "code",
        "created_at",
        "vocal_mix",
        "volume",
        "mic_gain",
        "lyric_mode",
        "now_index",
        "paused",
        "lan_origin",
        "lan_mic_port",
        "lan_mic_sample_rate",
        "lan_seen_at",
    )
    assert TABLES["queue"] == ("id", "room", "song_id", "position", "created_at")
    assert TABLES["users"] == (
        "id",
        "wechat_openid",
        "wechat_unionid",
        "device_id",
        "nickname",
        "avatar",
        "username",
        "username_key",
        "password_hash",
        "created_at",
    )
    assert TABLES["guest_song_counts"] == ("guest_key", "day", "used")
    assert TABLES["sessions"] == ("token", "user_id", "created_at", "expires_at")
    assert TABLES["login_tickets"] == (
        "id",
        "status",
        "user_id",
        "created_at",
        "expires_at",
    )
    assert TABLES["hosts"] == ("key", "room", "ua", "created_at", "last_seen")


def test_postgres_ddl_uses_bigint_for_epoch_ms():
    assert "created_at BIGINT" in POSTGRES_DDL
    assert "expires_at BIGINT" in POSTGRES_DDL
    assert "vocal_mix DOUBLE PRECISION" in POSTGRES_DDL
    assert "CREATE TABLE IF NOT EXISTS songs" in POSTGRES_DDL
    assert "CREATE TABLE IF NOT EXISTS login_tickets" in SQLITE_DDL


def test_adapt_sql_switches_placeholders():
    sql = "SELECT * FROM songs WHERE id=?"
    assert adapt_sql(sql, "sqlite") == sql
    assert adapt_sql(sql, "postgres") == "SELECT * FROM songs WHERE id=%s"


def test_postgres_url_detection():
    assert is_postgres_url("postgresql://postgres:x@host:5432/postgres")
    assert is_postgres_url(
        "postgres://postgres.abc:x@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    )
    assert not is_postgres_url("")
    assert not is_postgres_url("sqlite:///tmp/t.sqlite")


def test_init_db_creates_sqlite_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.delenv("LOVKTV_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    assert dialect(store.DB_PATH) == "sqlite"
    with store.connect() as conn:
        for name, cols in TABLES.items():
            assert table_columns(conn, name) >= set(cols)
    song = store.create_song("测试", "歌手", "ja")
    store.update_song(song["id"], status="ready", audio_source="netease")
    got = store.get_song(song["id"])
    assert got["title"] == "测试"
    assert got["audio_source"] == "netease"
    from lovktv.storage.room_store import ensure_room

    room = ensure_room("AB12CD")
    assert room["lyric_mode"] == "all"
    assert room["mic_gain"] == 80
    assert int(room["paused"] or 0) == 0


def test_overridden_sqlite_path_wins_over_postgres_url(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.setenv(
        "LOVKTV_DATABASE_URL", "postgresql://postgres:x@localhost:5432/postgres"
    )
    from lovktv.core.db import dialect

    assert dialect(tmp_path / "t.sqlite") == "sqlite"
