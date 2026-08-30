"""Point wallets, ledger, ad sessions and one-time claims."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from lovktv.core.db import execute
from lovktv.storage.store import connect, now_ms

_LOCK = threading.Lock()


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def wallet_balance(owner: str) -> int:
    if not owner:
        return 0
    with connect() as conn:
        row = execute(
            conn, "SELECT balance FROM point_wallets WHERE owner=?", (owner,)
        ).fetchone()
    return int(dict(row).get("balance") or 0) if row else 0


def apply_delta(owner: str, kind: str, delta: int, ref: str = "") -> int:
    if not owner or not delta:
        return wallet_balance(owner)
    now = now_ms()
    entry = uuid.uuid4().hex[:12]
    with _LOCK, connect() as conn:
        row = execute(
            conn, "SELECT balance FROM point_wallets WHERE owner=?", (owner,)
        ).fetchone()
        current = int(dict(row).get("balance") or 0) if row else 0
        nxt = current + int(delta)
        if nxt < 0:
            raise ValueError("积分不够")
        if row:
            execute(
                conn,
                "UPDATE point_wallets SET balance=?, updated_at=? WHERE owner=?",
                (nxt, now, owner),
            )
        else:
            execute(
                conn,
                "INSERT INTO point_wallets (owner, balance, created_at, updated_at) VALUES (?,?,?,?)",
                (owner, nxt, now, now),
            )
        execute(
            conn,
            "INSERT INTO point_ledger (id, owner, kind, delta, ref, created_at) VALUES (?,?,?,?,?,?)",
            (entry, owner, kind, int(delta), ref or "", now),
        )
    return nxt


def merge_wallets(src: str, dest: str) -> int:
    if not src or not dest or src == dest:
        return wallet_balance(dest)
    src_bal = wallet_balance(src)
    if src_bal:
        apply_delta(dest, "merge", src_bal, src)
        apply_delta(src, "merge", -src_bal, dest)
    return wallet_balance(dest)


def has_claim(owner: str, kind: str) -> bool:
    if not owner or not kind:
        return False
    with connect() as conn:
        row = execute(
            conn,
            "SELECT kind FROM point_claims WHERE owner=? AND kind=?",
            (owner, kind),
        ).fetchone()
    return bool(row)


def add_claim(owner: str, kind: str) -> bool:
    if not owner or not kind or has_claim(owner, kind):
        return False
    with _LOCK, connect() as conn:
        exists = execute(
            conn,
            "SELECT kind FROM point_claims WHERE owner=? AND kind=?",
            (owner, kind),
        ).fetchone()
        if exists:
            return False
        execute(
            conn,
            "INSERT INTO point_claims (owner, kind, created_at) VALUES (?,?,?)",
            (owner, kind, now_ms()),
        )
    return True


def create_ad_session(owner: str, placement: str, ad_id: str) -> dict[str, Any]:
    token = uuid.uuid4().hex
    now = now_ms()
    with _LOCK, connect() as conn:
        execute(
            conn,
            "INSERT INTO ad_sessions (token, owner, placement, ad_id, started_at) VALUES (?,?,?,?,?)",
            (token, owner, placement, ad_id, now),
        )
    return {
        "token": token,
        "owner": owner,
        "placement": placement,
        "ad_id": ad_id,
        "started_at": now,
        "completed_at": 0,
        "clicked": 0,
    }


def get_ad_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with connect() as conn:
        row = execute(
            conn, "SELECT * FROM ad_sessions WHERE token=?", (token,)
        ).fetchone()
    return _row(row)


def mark_ad_clicked(token: str) -> None:
    with _LOCK, connect() as conn:
        execute(
            conn, "UPDATE ad_sessions SET clicked=1 WHERE token=?", (token,)
        )


def mark_ad_completed(token: str) -> bool:
    now = now_ms()
    with _LOCK, connect() as conn:
        cur = execute(
            conn,
            "UPDATE ad_sessions SET completed_at=? WHERE token=? AND completed_at=0",
            (now, token),
        )
        return int(getattr(cur, "rowcount", 0) or 0) == 1


def list_wallets(limit: int = 80) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 80), 200))
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT owner, balance, updated_at FROM point_wallets ORDER BY updated_at DESC, owner DESC",
        ).fetchall()
    out = []
    for row in rows[:limit]:
        data = dict(row)
        out.append(
            {
                "owner": str(data.get("owner") or ""),
                "balance": int(data.get("balance") or 0),
                "updated_at": int(data.get("updated_at") or 0),
            }
        )
    return out


def list_ledger(owner: str = "", kind: str = "", limit: int = 80) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 80), 200))
    kind = str(kind or "").strip()
    with connect() as conn:
        if owner and kind:
            rows = execute(
                conn,
                "SELECT * FROM point_ledger WHERE owner=? AND kind=? ORDER BY created_at DESC, id DESC",
                (owner, kind),
            ).fetchall()
        elif owner:
            rows = execute(
                conn,
                "SELECT * FROM point_ledger WHERE owner=? ORDER BY created_at DESC, id DESC",
                (owner,),
            ).fetchall()
        elif kind:
            rows = execute(
                conn,
                "SELECT * FROM point_ledger WHERE kind=? ORDER BY created_at DESC, id DESC",
                (kind,),
            ).fetchall()
        else:
            rows = execute(
                conn,
                "SELECT * FROM point_ledger ORDER BY created_at DESC, id DESC",
            ).fetchall()
    out = []
    for row in rows[:limit]:
        data = dict(row)
        out.append(
            {
                "id": str(data.get("id") or ""),
                "owner": str(data.get("owner") or ""),
                "kind": str(data.get("kind") or ""),
                "delta": int(data.get("delta") or 0),
                "ref": str(data.get("ref") or ""),
                "created_at": int(data.get("created_at") or 0),
            }
        )
    return out


def points_total() -> int:
    with connect() as conn:
        row = execute(
            conn, "SELECT COALESCE(SUM(balance),0) AS n FROM point_wallets"
        ).fetchone()
    if not row:
        return 0
    data = dict(row)
    return int(data.get("n") or list(data.values())[0] or 0)


def completed_ads_today(owner: str, day_start_ms: int) -> int:
    if not owner:
        return 0
    with connect() as conn:
        row = execute(
            conn,
            "SELECT COUNT(*) AS n FROM ad_sessions WHERE owner=? AND completed_at>=?",
            (owner, day_start_ms),
        ).fetchone()
    if not row:
        return 0
    data = dict(row)
    return int(data.get("n") or data.get("count") or list(data.values())[0] or 0)
