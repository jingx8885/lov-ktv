from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from lovktv.agents.ja_lyrics import annotate_ja_lines
from lovktv.auth import (
    SESSION_COOKIE,
    auth_status,
    decode_state,
    done_login_path,
    encode_state,
    exchange_wechat_code,
    in_wechat,
    login_page_url,
    public_base,
    scan_login_url,
    wechat_authorize_url,
    wechat_ready,
)
from lovktv.catalog.fetch import open_preview_stream, resolve_audio_source, search_songs
from lovktv.catalog.mugen import is_mugen_kid
from lovktv.catalog.index import prefer_native_library, query_library
from lovktv.config import MEDIA_DIR, PUBLIC_URL, ROOT, SESSION_DAYS
from lovktv.oss import oss_ready, oss_status, public_url
from lovktv.host_volume import host_volume_meta, set_host_volume
from lovktv.jobs import process_import, process_realign, process_upload, resume_stuck_jobs, spawn
from lovktv.pipeline.lyrics import validate_timeline, write_manual_lrc, write_subtitles
from lovktv.pipeline.mdx_onnx import model_status
from lovktv.store import (
    bump,
    confirm_login_ticket,
    consume_confirmed_ticket,
    create_login_ticket,
    create_session,
    create_song,
    delete_session,
    delete_song,
    enqueue,
    ensure_room,
    get_login_ticket,
    get_song,
    init_db,
    list_songs,
    play_now,
    retry_query,
    room_snapshot,
    set_mix,
    skip,
    update_song,
    with_media_flags,
    upsert_device_user,
    upsert_wechat_user,
    user_from_session,
)

WEB = ROOT / "frontend" / "public"

class NoStoreHtmlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".html") or path in {"/", "/m.html", "/tv.html", "/login.html"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


app = FastAPI(title="lov-ktv")
app.add_middleware(NoStoreHtmlMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
_rooms: dict[str, set[WebSocket]] = {}
_peers: dict[WebSocket, dict] = {}
_mics: dict[str, str] = {}


def _request_base(request: Request) -> str:
    if PUBLIC_URL:
        return PUBLIC_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _current_user(request: Request) -> dict | None:
    return user_from_session(request.cookies.get(SESSION_COOKIE) or "")


def _set_session(response, token: str, request: Request) -> None:
    secure = request.url.scheme == "https" or public_base().startswith("https")
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )


def _clear_session(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _room_view(code: str, snap: dict | None = None) -> dict:
    room = dict(snap or room_snapshot(code))
    room["mic_on"] = bool(_mics.get(code))
    room["mic_peer"] = _mics.get(code) or ""
    room.update(host_volume_meta())
    if room.get("now_playing"):
        room["now_playing"] = with_media_flags(room["now_playing"])
    room["queue"] = [with_media_flags(item) or item for item in room.get("queue") or []]
    return room


async def _broadcast(code: str, payload: dict, skip: WebSocket | None = None) -> None:
    for peer in list(_rooms.get(code, set())):
        if peer is skip:
            continue
        try:
            await peer.send_json(payload)
        except Exception:
            _rooms.get(code, set()).discard(peer)
            _peers.pop(peer, None)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    resume_stuck_jobs()


@app.get("/api/host")
def api_host(request: Request) -> dict:
    origin = _request_base(request)
    return {
        "origin": origin,
        "process_origin": origin,
        "mode": "server",
        "phone_path": "/m.html?room=",
        "cache_ready": 0,
        "models": model_status(),
        "oss": oss_status(),
    }


@app.get("/api/auth/status")
def api_auth_status() -> dict:
    return auth_status()


@app.get("/api/auth/me")
def api_auth_me(request: Request) -> dict:
    return {"user": _current_user(request)}


@app.post("/api/auth/logout")
def api_auth_logout(request: Request) -> JSONResponse:
    delete_session(request.cookies.get(SESSION_COOKIE) or "")
    response = JSONResponse({"ok": True, "user": None})
    _clear_session(response)
    return response


@app.post("/api/auth/device")
def api_auth_device(request: Request, payload: dict = Body(default={})) -> JSONResponse:
    try:
        user = upsert_device_user(str(payload.get("device_id") or ""), str(payload.get("nickname") or ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    token = create_session(user["id"])
    response = JSONResponse({"user": user})
    _set_session(response, token, request)
    return response


@app.get("/api/auth/scan")
def api_auth_scan(
    request: Request,
    ticket: str = "",
    room: str = "",
    next: str = "",
) -> RedirectResponse:
    base = _request_base(request)
    dest = done_login_path(ticket, room, next)
    user = _current_user(request)
    if user:
        if ticket:
            try:
                confirm_login_ticket(ticket, user["id"])
            except ValueError:
                pass
        response = RedirectResponse(dest if dest.startswith("http") else f"{base}{dest}", status_code=302)
        return response
    if in_wechat(request.headers.get("user-agent") or "") and wechat_ready("mp"):
        redirect_uri = f"{base}/api/auth/wechat/callback"
        state = encode_state("silent", ticket, dest)
        try:
            url = wechat_authorize_url(redirect_uri, state, silent=True)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(url, status_code=302)
    return RedirectResponse(login_page_url(base, ticket=ticket, room=room, next_path=next), status_code=302)


@app.get("/api/auth/wechat/login")
def api_wechat_login(
    request: Request,
    silent: bool = False,
    quick: bool = False,
    ticket: str = "",
    next: str = "",
) -> RedirectResponse:
    use_silent = bool(silent) and wechat_ready("mp")
    use_quick = bool(quick) and wechat_ready("mp") and not use_silent
    if use_silent or use_quick:
        pass
    elif wechat_ready("web"):
        use_silent = False
        use_quick = False
    else:
        raise HTTPException(400, "还没配置微信开放平台 AppID")
    redirect_uri = f"{_request_base(request)}/api/auth/wechat/callback"
    if use_silent:
        kind = "silent"
    elif use_quick:
        kind = "quick"
    else:
        kind = "web"
    state = encode_state(kind, ticket, next)
    try:
        url = wechat_authorize_url(redirect_uri, state, quick=use_quick, silent=use_silent)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(url, status_code=302)


@app.get("/api/auth/wechat/callback")
def api_wechat_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    kind, ticket, next_path = decode_state(state)
    base = _request_base(request)
    if not code:
        return RedirectResponse(login_page_url(base, ticket=ticket, next_path=next_path, error="微信取消了授权"), 302)
    try:
        info = exchange_wechat_code(code, quick=kind == "quick", silent=kind in {"silent", "base"})
        user = upsert_wechat_user(info["openid"], info.get("unionid") or "", info.get("nickname") or "", info.get("avatar") or "")
    except ValueError as exc:
        return RedirectResponse(login_page_url(base, ticket=ticket, next_path=next_path, error=str(exc)), 302)
    if ticket:
        try:
            confirm_login_ticket(ticket, user["id"])
        except ValueError:
            pass
    dest = done_login_path(ticket, "", next_path)
    if not dest.startswith("http"):
        dest = f"{base}{dest}"
    response = RedirectResponse(dest, status_code=302)
    _set_session(response, create_session(user["id"]), request)
    return response


@app.post("/api/auth/qr")
def api_auth_qr(request: Request, payload: dict = Body(default={})) -> dict:
    ticket = create_login_ticket()
    room = str(payload.get("room") or "").upper()
    url = scan_login_url(_request_base(request), ticket=ticket["ticket"], room=room)
    return {**ticket, "url": url}


@app.get("/api/auth/qr/{ticket}")
def api_auth_qr_status(ticket: str, request: Request, claim: bool = False):
    row = get_login_ticket(ticket)
    if not row:
        raise HTTPException(404, "二维码无效")
    payload = {"status": row["status"], "expires_at": row["expires_at"]}
    if claim and row["status"] == "confirmed":
        user = consume_confirmed_ticket(ticket)
        if user:
            response = JSONResponse({"status": "ok", "user": user})
            _set_session(response, create_session(user["id"]), request)
            return response
    if row["status"] == "confirmed" and row.get("user_id"):
        payload["ready"] = True
    return payload


@app.post("/api/auth/qr/{ticket}/confirm")
def api_auth_qr_confirm(ticket: str, request: Request) -> dict:
    user = _current_user(request)
    if not user:
        raise HTTPException(401, "请先登录")
    try:
        confirm_login_ticket(ticket, user["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "user": user}


@app.get("/api/search")
def api_search(q: str, count: int = 10, page: int = 1) -> dict:
    if not q.strip():
        raise HTTPException(400, "缺少 q")
    try:
        return search_songs(q.strip(), count=count, page=page)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"搜索失败：{exc}") from exc


@app.get("/api/preview/{netease_id}/resolve")
def api_preview_resolve(netease_id: str, title: str = "", artist: str = "") -> dict:
    if not netease_id.isdigit():
        raise HTTPException(400, "无效的试听 id")
    source = resolve_audio_source(netease_id, title, artist)
    if not source:
        raise HTTPException(404, "这首暂时不能试听")
    return {"ok": True, "id": netease_id, "kind": source.get("kind"), "title": source.get("title") or title}


@app.get("/api/preview/{netease_id}")
def api_preview(netease_id: str, title: str = "", artist: str = ""):
    if not netease_id.isdigit():
        raise HTTPException(400, "无效的试听 id")
    resp, source = open_preview_stream(netease_id, title, artist)
    if resp is None:
        raise HTTPException(404, "这首暂时不能试听")
    ctype = str(resp.headers.get("Content-Type") or "audio/mpeg")

    def chunks():
        try:
            while True:
                data = resp.read(65536)
                if not data:
                    break
                yield data
        finally:
            resp.close()

    return StreamingResponse(chunks(), media_type=ctype, headers={"Cache-Control": "no-store"})


@app.post("/api/songs/import")
def api_import(payload: dict) -> dict:
    query = str(payload.get("query") or payload.get("title") or "").strip()
    if not query:
        raise HTTPException(400, "缺少 query")
    raw_id = str(payload.get("id") or "")
    language = str(payload.get("language") or ("ja" if is_mugen_kid(raw_id) else "zh"))
    song = create_song(
        title=str(payload.get("title") or query),
        artist=str(payload.get("artist") or ""),
        language=language,
        netease_id=raw_id,
    )
    spawn(
        process_import,
        song["id"],
        query,
        str(payload.get("id") or ""),
        payload.get("language"),
    )
    return song


@app.post("/api/songs")
async def api_upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(""),
    language: str = Form("zh"),
    lyrics: str = Form(""),
) -> dict:
    song = create_song(title or file.filename or "未命名", artist, language)
    dest = MEDIA_DIR / song["id"] / "original.mp3"
    with dest.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    if lyrics.strip():
        (MEDIA_DIR / song["id"] / "lyrics.lrc").write_text(lyrics, encoding="utf-8")
    spawn(process_upload, song["id"], dest, language)
    return song


@app.post("/api/agents/ja-lyrics")
def api_ja_lyrics(payload: dict = Body(default={})) -> dict:
    lines = [str(item) for item in (payload.get("lines") or []) if str(item).strip()]
    if not lines:
        raise HTTPException(400, "缺少 lines")
    try:
        return annotate_ja_lines(
            lines,
            title=str(payload.get("title") or ""),
            artist=str(payload.get("artist") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"日语注音失败：{exc}") from exc


@app.post("/api/songs/{song_id}/realign")
def api_realign(song_id: str, payload: dict = Body(default={})) -> dict:
    song = get_song(song_id)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    spawn(
        process_realign,
        song_id,
        payload.get("language") or song.get("language"),
        bool(payload.get("rebuild_mtv")),
    )
    return {"ok": True, "song_id": song_id, "status": "aligning"}


@app.put("/api/songs/{song_id}/lyrics")
def api_save_lyrics(song_id: str, payload: dict = Body(default={})) -> dict:
    song = get_song(song_id)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    try:
        timeline = validate_timeline(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    write_subtitles(timeline, MEDIA_DIR / song_id)
    write_manual_lrc(MEDIA_DIR / song_id, timeline["cues"])
    return {"ok": True, "song_id": song_id, "cues": len(timeline["cues"])}


@app.delete("/api/songs/{song_id}")
def api_delete_song(song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    if not delete_song(song_id):
        raise HTTPException(404, "歌曲不存在")
    return {"ok": True, "song_id": song_id}


@app.post("/api/songs/{song_id}/retry")
def api_retry_song(song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    if song.get("status") != "failed":
        raise HTTPException(400, "只有失败的歌可以重试")
    update_song(song_id, status="queued", error="")
    spawn(
        process_import,
        song_id,
        retry_query(song),
        str(song.get("netease_id") or ""),
        song.get("language"),
    )
    return {"ok": True, "song_id": song_id, "status": "queued"}


@app.get("/api/songs")
def api_songs(
    q: str = "",
    by: str = "all",
    letter: str = "",
    page: int | None = None,
    count: int = 12,
) -> dict:
    songs = prefer_native_library([with_media_flags(song) or song for song in list_songs()])
    if page is None and not q and not letter:
        return {"songs": songs, "total": len(songs)}
    return query_library(songs, q=q, by=by, letter=letter, page=page or 1, count=count)


@app.get("/api/songs/{song_id}")
def api_song(song_id: str) -> dict:
    song = with_media_flags(get_song(song_id))
    if not song:
        raise HTTPException(404, "歌曲不存在")
    folder = MEDIA_DIR / song_id
    song["files"] = sorted(path.name for path in folder.iterdir()) if folder.exists() else []
    return song


@app.post("/api/rooms")
def api_create_room() -> dict:
    return ensure_room()


@app.get("/api/rooms/{code}")
def api_room(code: str) -> dict:
    return _room_view(code.upper())


@app.post("/api/rooms/{code}/queue")
def api_enqueue(code: str, payload: dict) -> dict:
    song_id = str(payload.get("song_id") or "")
    if not get_song(song_id):
        raise HTTPException(404, "歌曲不存在")
    try:
        return enqueue(code.upper(), song_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rooms/{code}/bump")
def api_bump(code: str, payload: dict) -> dict:
    return bump(code.upper(), str(payload.get("id") or ""))


@app.post("/api/rooms/{code}/skip")
def api_skip(code: str) -> dict:
    return skip(code.upper())


@app.post("/api/rooms/{code}/play")
def api_play(code: str, payload: dict) -> dict:
    try:
        return play_now(code.upper(), str(payload.get("id") or ""), str(payload.get("song_id") or ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rooms/{code}/mix")
async def api_mix(code: str, payload: dict) -> dict:
    code = code.upper()
    snap = set_mix(code, payload.get("vocal_mix"), payload.get("volume"), payload.get("mic_gain"))
    if payload.get("volume") is not None:
        set_host_volume(int(payload.get("volume") or 0))
    view = _room_view(code, snap)
    await _broadcast(code, {"type": "snapshot", "room": view})
    return view


@app.websocket("/ws/rooms/{code}")
async def ws_room(ws: WebSocket, code: str) -> None:
    code = code.upper()
    await ws.accept()
    _rooms.setdefault(code, set()).add(ws)
    _peers[ws] = {"code": code, "peer": "", "role": ""}
    await ws.send_json({"type": "snapshot", "room": _room_view(code)})
    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "hello":
                _peers[ws] = {
                    "code": code,
                    "peer": str(msg.get("peer") or ""),
                    "role": str(msg.get("role") or ""),
                }
                await _broadcast(
                    code,
                    {
                        "type": "peer",
                        "event": "join",
                        "peer": _peers[ws]["peer"],
                        "role": _peers[ws]["role"],
                    },
                    skip=ws,
                )
                continue
            if action == "rtc":
                kind = str(msg.get("kind") or "")
                peer = str(msg.get("from") or _peers.get(ws, {}).get("peer") or "")
                if kind == "offer" and peer:
                    _mics[code] = peer
                if kind == "hangup" and _mics.get(code) == peer:
                    _mics.pop(code, None)
                await _broadcast(
                    code,
                    {"type": "rtc", **{k: v for k, v in msg.items() if k != "action"}},
                    skip=ws,
                )
                if kind in {"offer", "hangup"}:
                    await _broadcast(code, {"type": "snapshot", "room": _room_view(code)})
                continue
            if action == "mic":
                peer = str(msg.get("from") or _peers.get(ws, {}).get("peer") or "")
                if msg.get("on"):
                    if peer:
                        _mics[code] = peer
                elif _mics.get(code) == peer or not peer:
                    _mics.pop(code, None)
                if msg.get("mic_gain") is not None:
                    set_mix(code, mic_gain=msg.get("mic_gain"))
                await _broadcast(code, {"type": "snapshot", "room": _room_view(code)})
                continue
            if action == "skip":
                snap = skip(code)
            elif action == "bump":
                snap = bump(code, str(msg.get("id") or ""))
            elif action == "enqueue":
                try:
                    snap = enqueue(code, str(msg.get("song_id") or ""))
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})
                    continue
            elif action == "mix":
                snap = set_mix(code, msg.get("vocal_mix"), msg.get("volume"), msg.get("mic_gain"))
                if msg.get("volume") is not None:
                    set_host_volume(int(msg.get("volume") or 0))
            else:
                await ws.send_json({"type": "error", "message": "未知命令"})
                continue
            await _broadcast(code, {"type": "snapshot", "room": _room_view(code, snap)})
    except WebSocketDisconnect:
        info = _peers.pop(ws, {})
        _rooms.get(code, set()).discard(ws)
        peer = str(info.get("peer") or "")
        if peer and _mics.get(code) == peer:
            _mics.pop(code, None)
            await _broadcast(code, {"type": "rtc", "kind": "hangup", "from": peer})
            await _broadcast(code, {"type": "snapshot", "room": _room_view(code)})
        await _broadcast(
            code,
            {"type": "peer", "event": "leave", "peer": peer, "role": info.get("role") or ""},
        )


@app.get("/media/{song_id}/{name}")
def media(song_id: str, name: str):
    root = MEDIA_DIR.resolve()
    path = (root / song_id / name).resolve()
    if root not in path.parents:
        raise HTTPException(404)
    if path.exists():
        return FileResponse(
            path,
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache, must-revalidate"},
        )
    if oss_ready():
        return RedirectResponse(public_url(song_id, name), status_code=302)
    raise HTTPException(404)


@app.get("/m.html")
def mobile_page() -> FileResponse:
    path = WEB / "m.html"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(
        path,
        media_type="text/html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/login.html")
def login_page() -> FileResponse:
    path = WEB / "login.html"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(
        path,
        media_type="text/html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
