"""SQLite locally / in tests; PostgreSQL (Supabase) when a postgres URL is set."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from lovktv.core.config import DB_PATH as DEFAULT_DB_PATH
from lovktv.core.config import MEDIA_DIR
from lovktv.core.schema import POSTGRES_DDL, ROOM_MIGRATIONS, SQLITE_DDL


def database_url() -> str:
    return (
        os.environ.get("LOVKTV_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    ).strip()


def is_postgres_url(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://"))


def dialect(sqlite_path: Path | str | None = None) -> str:
    url = database_url()
    path = Path(sqlite_path) if sqlite_path is not None else DEFAULT_DB_PATH
    if is_postgres_url(url) and Path(path) == Path(DEFAULT_DB_PATH):
        return "postgres"
    return "sqlite"


def adapt_sql(sql: str, kind: str | None = None) -> str:
    if (kind or dialect()) != "postgres":
        return sql
    return sql.replace("?", "%s")


def _pg_connect():
    import psycopg
    from psycopg.rows import dict_row

    url = database_url()
    kwargs: dict[str, Any] = {"row_factory": dict_row}
    if "pooler.supabase.com" in url or ":6543" in url:
        kwargs["prepare_threshold"] = None
    return psycopg.connect(url, **kwargs)


def connect(sqlite_path: Path | str | None = None):
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    if dialect(sqlite_path) == "postgres":
        return _pg_connect()
    path = Path(sqlite_path) if sqlite_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    return conn.execute(adapt_sql(sql, _conn_dialect(conn)), tuple(params))


def executescript(conn: Any, sql: str) -> None:
    if _conn_dialect(conn) == "sqlite":
        conn.executescript(sql)
        return
    for statement in _split_sql(sql):
        conn.execute(statement)


def _split_sql(sql: str) -> list[str]:
    parts = []
    for chunk in sql.split(";"):
        stmt = "\n".join(
            line for line in chunk.splitlines() if not line.strip().startswith("--")
        ).strip()
        if stmt:
            parts.append(stmt)
    return parts


def _conn_dialect(conn: Any) -> str:
    if isinstance(conn, sqlite3.Connection):
        return "sqlite"
    return "postgres"


def table_columns(conn: Any, table: str) -> set[str]:
    if _conn_dialect(conn) == "sqlite":
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}
    rows = execute(
        conn,
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
        (table,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


def init_schema(conn: Any) -> None:
    kind = _conn_dialect(conn)
    executescript(conn, SQLITE_DDL if kind == "sqlite" else POSTGRES_DDL)
    cols = table_columns(conn, "rooms")
    for name, decl in ROOM_MIGRATIONS:
        if name not in cols:
            conn.execute(f"ALTER TABLE rooms ADD COLUMN {name} {decl}")
