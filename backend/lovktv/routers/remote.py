"""Self-hosted remote content reports, with an operator-only moderation queue."""

import time
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

from lovktv.api.models import RoomCommandPayload
from lovktv.core.db import connect, execute
from lovktv.identity.admin import require_admin
from lovktv.identity.remote_keys import is_member, issue_key, key_info, require_key
from lovktv.locale.i18n import localize_song, request_lang
from lovktv.routers import learn, media, recite, rooms
from lovktv.services.http import current_user
from lovktv.services.room_runtime import room_view
from lovktv.storage import store
from lovktv.storage.store import with_media_flags

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
        execute(
            conn,
            "INSERT INTO remote_reports(id,song_id,reason,created_at) VALUES(?,?,?,?)",
            (
                identifier,
                payload.song_id,
                payload.reason.strip(),
                int(time.time() * 1000),
            ),
        )
    return {"id": identifier, "ok": True}


@router.get("/api/admin/remote-reports")
def reports(request: Request):
    require_admin(request)
    with connect(store.DB_PATH) as conn:
        rows = execute(
            conn, "SELECT * FROM remote_reports ORDER BY created_at LIMIT 200"
        ).fetchall()
    return {"reports": [dict(row) for row in rows]}


@router.delete("/api/admin/remote-reports/{report_id}")
def resolve_report(request: Request, report_id: str):
    require_admin(request)
    with connect(store.DB_PATH) as conn:
        execute(conn, "DELETE FROM remote_reports WHERE id=?", (report_id,))
    return {"ok": True}


# Only cookie sessions can manage keys; API keys never authorize account/billing APIs.


def account(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先登录")
    return user


@router.get("/api/account/remote-key")
def get_key(user=Depends(account)):
    return JSONResponse(
        {"eligible": is_member(user), "key": key_info(user["id"])},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/account/remote-key", status_code=201)
def create_key(user=Depends(account)):
    if not is_member(user):
        raise HTTPException(403, "仅有效会员可申请 API key")
    return JSONResponse(
        {"api_key": issue_key(user["id"])},
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/api/account/remote-key")
def delete_key(user=Depends(account)):
    with store.connect() as conn:
        store.execute(
            conn, "DELETE FROM remote_api_keys WHERE user_id=?", (user["id"],)
        )
    return {"ok": True}


def permitted_song(song):
    # 白名单：上传和搜歌来源都可点；status ready 才进遥控/点歌链路。
    return bool(
        song
        and song.get("status") == "ready"
        and song.get("audio_source") in {"upload", "bilibili", "mugen", "soundcloud"}
    )


def safe_song(song):
    return {
        key: song[key]
        for key in ("id", "song_id", "title", "artist", "status", "media_rev")
        if key in song
    }


def safe_room(view):
    result = {key: view.get(key) for key in ("code", "paused", "volume")}
    result["queue"] = [
        safe_song(s)
        for s in view.get("queue", [])
        if permitted_song(store.get_song(s.get("song_id") or s.get("id")))
    ]
    song = view.get("now_playing")
    result["now_playing"] = (
        safe_song(song)
        if song
        and permitted_song(store.get_song(song.get("song_id") or song.get("id")))
        else None
    )
    return result


# This namespace always enforces the iOS policy, even if the client omits its platform header.
ios_router = APIRouter(prefix="/api/remote/ios", dependencies=[Depends(require_key)])


@ios_router.get("/songs")
def ios_songs(q: str = "", page: int = 1, count: int = 20):
    songs = [
        safe_song(s)
        for s in store.list_songs()
        if permitted_song(s)
        and q.casefold() in (s.get("title", "") + " " + s.get("artist", "")).casefold()
    ]
    # 补 media_rev：封面 URL 需要，与 /api/songs 一致
    for s in songs:
        rev = store.media_flags(s["id"]).get("media_rev")
        if rev:
            s["media_rev"] = rev
    count = max(1, min(count, 100))
    start = (max(page, 1) - 1) * count
    return {"songs": songs[start : start + count], "total": len(songs)}


@ios_router.get("/rooms/{code}")
def ios_room(code: str):
    return safe_room(room_view(code.upper()))


@ios_router.post("/rooms/{code}/{command}")
async def ios_command(
    request: Request, code: str, command: str, payload: RoomCommandPayload
):
    if command == "queue":
        if not permitted_song(store.get_song(str(payload.song_id or ""))):
            raise HTTPException(404, "内容不可用")
        # Existing quota/points identity is scoped to this authenticated request only.
        request.state.remote_user = require_key(request)
        view = await rooms.api_enqueue(request, code, payload)
    elif command == "skip":
        view = await rooms.api_skip(request, code)
    elif command == "play":
        if payload.song_id or payload.id or payload.item_id:
            raise HTTPException(400, "请从曲库点歌")
        view = await rooms.api_play(request, code, payload)
    elif command == "mix":
        view = await rooms.api_mix(request, code, payload)
    else:
        raise HTTPException(404, "不支持此操作")
    return safe_room(view)


@ios_router.post("/reports", status_code=201)
def ios_report(payload: Report):
    if not permitted_song(store.get_song(payload.song_id)):
        raise HTTPException(404, "内容不可用")
    return report_content(payload)


@ios_router.get("/songs/{song_id}")
def ios_song(request: Request, song_id: str):
    song = store.get_song(song_id)
    if not permitted_song(song):
        raise HTTPException(404, "内容不可用")
    song = localize_song(request_lang(request), with_media_flags(song)) or {}
    folder = store.MEDIA_DIR / song_id
    song["files"] = (
        sorted(path.name for path in folder.iterdir()) if folder.exists() else []
    )
    song.setdefault("id", song_id)
    return song


def _permit_media(song_id: str) -> None:
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", song_id) or not permitted_song(
        store.get_song(song_id)
    ):
        raise HTTPException(404, "内容不可用")


# 成品媒体按文件名放行：歌词/伴奏/封面/视频与自建服 /media 完全同一套逻辑，
# 已发布的走 OSS 302，未发布的读本机文件。
IOS_MEDIA_NAMES = {
    "original.mp3",
    "instrumental.wav",
    "karaoke.m4a",
    "guide.m4a",
    "mtv.mp4",
    "cover.jpg",
    "lyrics.json",
    "lyrics.lrc",
    "lyrics.elrc",
    "lyrics.ass",
}


@ios_router.get("/media/{song_id}")
def ios_media(song_id: str, request: Request):
    _permit_media(song_id)
    return media._serve_media(song_id, "original.mp3", request, store.MEDIA_DIR)


@ios_router.get("/media/{song_id}/{name}")
def ios_media_file(song_id: str, name: str, request: Request):
    if name not in IOS_MEDIA_NAMES:
        raise HTTPException(404, "内容不可用")
    _permit_media(song_id)
    return media._serve_media(song_id, name, request, store.MEDIA_DIR)


# 学习模块与自建服 /api/learn/* 完全同一套 handler：这里只做
# 白名单收口（member key + 曲目来源策略）并把身份落到 remote_user，
# 让学习进度/单词本挂在登录用户上、跨设备同步。

def _learn_owner(request: Request, user: dict) -> None:
    request.state.remote_user = user


def _permit_learn_song(request: Request, song_id: str, user: dict) -> None:
    _learn_owner(request, user)
    if not permitted_song(store.get_song(song_id)):
        raise HTTPException(404, "内容不可用")


@ios_router.get("/songs/{song_id}/learn/campaign")
def ios_learn_campaign(
    request: Request, song_id: str, user: dict = Depends(require_key)
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_learn_campaign(request, song_id)


@ios_router.get("/songs/{song_id}/learn/lesson")
def ios_learn_lesson(
    request: Request,
    song_id: str,
    unit: str = "u0",
    skill: str = "word",
    user: dict = Depends(require_key),
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_learn_lesson(request, song_id, unit, skill)


@ios_router.post("/songs/{song_id}/learn/lesson")
def ios_learn_lesson_submit(
    request: Request,
    song_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(require_key),
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_learn_lesson_submit(request, song_id, body)


@ios_router.get("/songs/{song_id}/learn/mistakes")
def ios_learn_mistakes(
    request: Request, song_id: str, user: dict = Depends(require_key)
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_learn_mistakes(request, song_id)


@ios_router.get("/songs/{song_id}/learn/review")
def ios_learn_review(
    request: Request, song_id: str, user: dict = Depends(require_key)
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_learn_review(request, song_id)


@ios_router.post("/songs/{song_id}/learn/review")
def ios_learn_review_submit(
    request: Request,
    song_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(require_key),
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_learn_review_submit(request, song_id, body)


@ios_router.get("/songs/{song_id}/learn/words")
def ios_song_words(
    request: Request, song_id: str, user: dict = Depends(require_key)
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_song_words(request, song_id)


@ios_router.post("/songs/{song_id}/learn/words/setup")
def ios_song_words_setup(
    request: Request,
    song_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(require_key),
) -> dict:
    _permit_learn_song(request, song_id, user)
    return learn.api_song_words_setup(request, song_id, body)


@ios_router.get("/learn/deck")
def ios_recite_deck(
    request: Request,
    deck: str = "word",
    cards: int = 1,
    song_id: str = "",
    user: dict = Depends(require_key),
) -> dict:
    _learn_owner(request, user)
    return recite.api_recite_deck(request, deck, cards, song_id)


@ios_router.post("/learn/cards")
def ios_recite_card_add(
    request: Request,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(require_key),
) -> dict:
    _learn_owner(request, user)
    return recite.api_recite_card_add(request, body)


@ios_router.delete("/learn/cards/{card_id}")
def ios_recite_card_drop(
    request: Request, card_id: str, user: dict = Depends(require_key)
) -> dict:
    _learn_owner(request, user)
    return recite.api_recite_card_drop(request, card_id)


@ios_router.get("/learn/words")
def ios_words_list(
    request: Request,
    state: str = "all",
    song_id: str = "",
    user: dict = Depends(require_key),
) -> dict:
    _learn_owner(request, user)
    return recite.api_words_list(request, state, song_id)


@ios_router.post("/learn/words/restore")
def ios_words_restore(
    request: Request,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(require_key),
) -> dict:
    _learn_owner(request, user)
    return recite.api_words_restore(request, body)


@ios_router.get("/learn/session")
def ios_recite_session(
    request: Request,
    deck: str = "word",
    size: int = 0,
    song_id: str = "",
    user: dict = Depends(require_key),
) -> dict:
    _learn_owner(request, user)
    return recite.api_recite_session(request, deck, size, song_id)


@ios_router.post("/learn/session")
def ios_recite_session_submit(
    request: Request,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(require_key),
) -> dict:
    _learn_owner(request, user)
    return recite.api_recite_session_submit(request, body)


router.include_router(ios_router)
