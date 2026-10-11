"""Self-hosted remote content reports, with an operator-only moderation queue."""
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

from lovktv.core.db import connect, execute
from lovktv.identity.admin import require_admin
from lovktv.storage import store

router = APIRouter()


class Report(BaseModel):
    song_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


@router.post("/api/remote/reports", status_code=201)
def report_content(payload: Report):
    if not payload.reason.strip():
        raise HTTPException(422, "举报原因不能为空")
    if not store.get_song(payload.song_id):
        raise HTTPException(404, "歌曲不存在")
    with connect(store.DB_PATH) as conn:
        # Bound anonymous intake even on private servers; operators clear handled reports.
        row = execute(conn, "SELECT COUNT(*) AS n FROM remote_reports").fetchone()
        if dict(row)["n"] >= 10000:
            raise HTTPException(429, "举报队列已满，请联系服务器管理员")
        identifier = uuid.uuid4().hex
        execute(conn, "INSERT INTO remote_reports(id,song_id,reason,created_at) VALUES(?,?,?,?)",
                (identifier, payload.song_id, payload.reason.strip(), int(time.time() * 1000)))
    return {"id": identifier, "ok": True}


@router.get("/api/admin/remote-reports")
def reports(request: Request):
    require_admin(request)
    with connect(store.DB_PATH) as conn:
        rows = execute(conn, "SELECT * FROM remote_reports ORDER BY created_at LIMIT 200").fetchall()
    return {"reports": [dict(row) for row in rows]}


@router.delete("/api/admin/remote-reports/{report_id}")
def resolve_report(request: Request, report_id: str):
    require_admin(request)
    with connect(store.DB_PATH) as conn:
        execute(conn, "DELETE FROM remote_reports WHERE id=?", (report_id,))
    return {"ok": True}
