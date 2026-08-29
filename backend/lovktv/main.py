from __future__ import annotations

import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from urllib.parse import quote

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from lovktv.agents.ja_lyrics import agent_status, annotate_ja_lines
from lovktv.api_models import RoomCommandPayload, RoomLanPayload
from lovktv.assets import VersionedStaticFiles, asset_rev, versioned_response
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
from lovktv.catalog.fetch import is_preview_id, open_preview_stream, resolve_audio_source, search_songs
from lovktv.catalog.mugen import is_mugen_kid
from lovktv.catalog.index import prefer_native_library, query_library, song_letter
from lovktv.apps import catalog as apps_catalog, download_apk, require_upload_token, save_apk
from lovktv.config import MEDIA_DIR, PUBLIC_URL, ROOT, SESSION_DAYS
from lovktv.db import dialect as db_dialect
from lovktv.oss import ensure_bucket_cors, oss_ready, oss_status, public_url
from lovktv.host_volume import host_volume_meta, set_host_volume
from lovktv.i18n import localize_error_text, localize_exc, localize_song, request_lang, t as i18n_t, translate, ws_lang
from lovktv.jobs import job_queue, process_import, process_realign, process_upload, resume_stuck_jobs, spawn
from lovktv.learn import build_learn_quiz
from lovktv.pipeline.lyrics import validate_timeline, write_manual_lrc, write_subtitles
from lovktv.pipeline.mdx_onnx import model_status
from lovktv.room_service import RoomCommand, room_service
from lovktv.room_store import ensure_room_for_host, remember_host_room, room_for_hosts, set_room_lan
from lovktv.timeline_contract import normalize_timeline
from lovktv.room_contract import normalize_playback_event
from lovktv import store
from lovktv.store import (
    confirm_login_ticket,
    consume_confirmed_ticket,
    create_login_ticket,
    create_session,
    create_song,
    delete_session,
    delete_song,
    get_login_ticket,
    host_keys,
    get_song,
    init_db,
    list_songs,
    retry_query,
    update_song,
    with_media_flags,
    upsert_device_user,
    upsert_wechat_user,
    user_from_session,
)

_PUBLIC = ROOT / "frontend" / "public"
_DIST = ROOT / "frontend" / "frontend-dist"
WEB = _DIST if (_DIST / "manifest.json").is_file() else _PUBLIC
HOST_COOKIE = "lovktv_host"
HOST_COOKIE_DAYS = 400

class NoStoreHtmlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".html") or path in {"/", "/m.html", "/tv.html", "/login.html"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize background services when the ASGI app starts.

    FastAPI's ``on_event`` hooks are deprecated and are not guaranteed to be
    composed correctly when applications are mounted.  A lifespan context
    keeps the same startup ordering while giving TestClient and production
    servers one canonical lifecycle entry point.
    """
    from lovktv.catalog.mugen_index import prefetch_index

    _app.state.ready = False
    job_queue.start()
    try:
        init_db()
        resume_stuck_jobs()
        prefetch_index()
        if oss_ready():
            try:
                print(f"[lovktv] oss cors {ensure_bucket_cors()}", flush=True)
            except Exception as exc:
                print(f"[lovktv] oss cors skipped: {exc}", flush=True)
        _app.state.ready = True
        yield
    finally:
        _app.state.ready = False
        stopped = job_queue.stop()
        if not stopped and job_queue.health()["running"]:
            print("[lovktv] job worker did not stop before shutdown timeout", flush=True)


app = FastAPI(title="lov-ktv", lifespan=lifespan)
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


def _request_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        raw = (request.headers.get(header) or "").strip()
        if raw:
            return raw.split(",")[0].strip()
    return request.client.host if request.client else ""


def _host_machine(request: Request) -> str:
    cookie = (request.cookies.get(HOST_COOKIE) or "").strip()
    header = (request.headers.get("x-lovktv-machine") or "").strip()
    mid = cookie or header
    return "".join(ch for ch in mid if ch.isalnum() or ch in "-_")[:64]


def _host_keys(request: Request) -> list[str]:
    return host_keys(_host_machine(request), request.headers.get("user-agent") or "", _request_ip(request))


def _bind_host(request: Request, room: str) -> str:
    machine = _host_machine(request)
    token = machine if len(machine) >= 8 else store.new_id()
    keys = host_keys(token, request.headers.get("user-agent") or "", _request_ip(request))
    remember_host_room(keys, room, request.headers.get("user-agent") or "")
    return token


def _set_host_cookie(response: JSONResponse, request: Request, token: str) -> JSONResponse:
    if not token:
        return response
    secure = request.url.scheme == "https" or public_base().startswith("https")
    response.set_cookie(
        HOST_COOKIE,
        token,
        max_age=HOST_COOKIE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )
    return response


def _fail(request: Request, status: int, key: str, **vars) -> None:
    raise HTTPException(status, i18n_t(request, key, **vars))


def _room_view(code: str, snap: dict | None = None, lang: str = "zh") -> dict:
    room = dict(snap or room_service.snapshot(code))
    room["mic_on"] = bool(_mics.get(code))
    room["mic_peer"] = _mics.get(code) or ""
    room.update(host_volume_meta())
    if room.get("now_playing"):
        room["now_playing"] = localize_song(lang, with_media_flags(room["now_playing"]))
    room["queue"] = [localize_song(lang, with_media_flags(item) or item) for item in room.get("queue") or []]
    room["paused"] = bool(int(room.get("paused") or 0))
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


def _run_room_command(code: str, command: RoomCommand) -> dict:
    """Execute a room command and apply host-only side effects.

    The service owns room semantics; this adapter is deliberately kept in the
    transport layer because changing the physical host volume is not a room
    database concern.
    """

    snap = room_service.execute(code, command)
    if command.volume is not None:
        set_host_volume(int(command.volume or 0))
    return snap


@app.get("/healthz", include_in_schema=False)
def healthz(request: Request) -> JSONResponse:
    """Readiness probe used by Compose and external monitors."""
    worker = job_queue.health()
    ready = bool(getattr(request.app.state, "ready", False)) and worker["running"]
    payload = {"status": "ok" if ready else "starting", "ready": ready, "worker": worker}
    return JSONResponse(payload, status_code=200 if ready else 503)


@app.get("/api/host")
def api_host(request: Request) -> dict:
    origin = _request_base(request)
    return {
        "origin": origin,
        "process_origin": origin,
        "mode": "server",
        "phone_path": "/m.html?room=",
        "cache_ready": 0,
        "mic_port": 0,
        "mic_sample_rate": 48000,
        "models": model_status(),
        "oss": oss_status(),
        "agent": agent_status(),
        "database": db_dialect(store.DB_PATH),
        "asset_rev": asset_rev(WEB),
        "worker": job_queue.health(),
    }


@app.get("/api/apps")
def api_apps() -> dict:
    return apps_catalog()


@app.get("/api/apps/{channel}")
@app.get("/apps/{channel}.apk")
def api_app_download(channel: str):
    return download_apk(channel)


@app.post("/api/apps/{channel}")
async def api_app_upload(
    channel: str,
    request: Request,
    file: UploadFile = File(...),
    version: str = Form(""),
) -> dict:
    require_upload_token(request)
    return save_apk(channel, file.file, version)


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
        raise HTTPException(400, localize_exc(request, exc)) from exc
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
            raise HTTPException(400, localize_exc(request, exc)) from exc
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
        _fail(request, 400, "api.wechat_not_configured")
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
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return RedirectResponse(url, status_code=302)


@app.get("/api/auth/wechat/callback")
def api_wechat_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    kind, ticket, next_path = decode_state(state)
    base = _request_base(request)
    if not code:
        return RedirectResponse(login_page_url(base, ticket=ticket, next_path=next_path, error="api.wechat_denied"), 302)
    try:
        info = exchange_wechat_code(code, quick=kind == "quick", silent=kind in {"silent", "base"})
        user = upsert_wechat_user(info["openid"], info.get("unionid") or "", info.get("nickname") or "", info.get("avatar") or "")
    except ValueError as exc:
        return RedirectResponse(login_page_url(base, ticket=ticket, next_path=next_path, error=localize_exc(request, exc)), 302)
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
        _fail(request, 404, "api.qr_invalid")
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
        _fail(request, 401, "api.need_login")
    try:
        confirm_login_ticket(ticket, user["id"])
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    return {"ok": True, "user": user}


@app.get("/api/search")
def api_search(request: Request, q: str, count: int = 10, page: int = 1) -> dict:
    if not q.strip():
        _fail(request, 400, "api.missing_q")
    try:
        return search_songs(q.strip(), count=count, page=page)
    except Exception as exc:  # noqa: BLE001
        _fail(request, 502, "api.search_failed", exc=exc)


@app.get("/api/preview/{song_id}/resolve")
def api_preview_resolve(request: Request, song_id: str, title: str = "", artist: str = "", media: str = "") -> dict:
    if is_mugen_kid(song_id):
        return {"ok": True, "id": song_id, "kind": "mugen", "title": title}
    if not is_preview_id(song_id):
        _fail(request, 400, "api.bad_preview_id")
    source = resolve_audio_source(song_id, title, artist)
    if not source:
        _fail(request, 404, "api.preview_unavailable")
    return {"ok": True, "id": song_id, "kind": source.get("kind"), "title": source.get("title") or title}


@app.get("/api/preview/{song_id}")
def api_preview(request: Request, song_id: str, title: str = "", artist: str = "", media: str = ""):
    if not is_preview_id(song_id):
        _fail(request, 400, "api.bad_preview_id")
    resp, source = open_preview_stream(song_id, title, artist, media=media)
    if resp is None:
        _fail(request, 404, "api.preview_unavailable")
    ctype = str(resp.headers.get("Content-Type") or "audio/mpeg")
    if source.get("kind") == "bilibili" and "html" not in ctype.lower():
        ctype = "audio/mp4"

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
def api_import(request: Request, payload: dict) -> dict:
    query = str(payload.get("query") or payload.get("title") or "").strip()
    if not query:
        _fail(request, 400, "api.missing_query")
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
        language,
    )
    return song


@app.post("/api/songs")
async def api_upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(""),
    language: str = Form("zh"),
    lyrics: str = Form(""),
    request: Request = None,  # FastAPI injects
) -> dict:
    song = create_song(title or file.filename or i18n_t(request, "api.unnamed"), artist, language)
    dest = MEDIA_DIR / song["id"] / "original.mp3"
    with dest.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    if lyrics.strip():
        (MEDIA_DIR / song["id"] / "lyrics.lrc").write_text(lyrics, encoding="utf-8")
    spawn(process_upload, song["id"], dest, language)
    return song


@app.post("/api/agents/ja-lyrics")
def api_ja_lyrics(request: Request, payload: dict = Body(default={})) -> dict:
    lines = [str(item) for item in (payload.get("lines") or []) if str(item).strip()]
    if not lines:
        _fail(request, 400, "api.missing_lines")
    try:
        return annotate_ja_lines(
            lines,
            title=str(payload.get("title") or ""),
            artist=str(payload.get("artist") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        _fail(request, 502, "api.ja_annotate_failed", exc=exc)


@app.post("/api/songs/{song_id}/realign")
def api_realign(request: Request, song_id: str, payload: dict = Body(default={})) -> dict:
    song = get_song(song_id)
    if not song:
        _fail(request, 404, "api.song_not_found")
    spawn(
        process_realign,
        song_id,
        payload.get("language") or song.get("language"),
        bool(payload.get("rebuild_mtv")),
    )
    return {"ok": True, "song_id": song_id, "status": "aligning"}


@app.put("/api/songs/{song_id}/lyrics")
def api_save_lyrics(request: Request, song_id: str, payload: dict = Body(default={})) -> dict:
    song = get_song(song_id)
    if not song:
        _fail(request, 404, "api.song_not_found")
    try:
        timeline = validate_timeline(payload)
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    write_subtitles(timeline, MEDIA_DIR / song_id)
    write_manual_lrc(MEDIA_DIR / song_id, timeline["cues"])
    return {"ok": True, "song_id": song_id, "cues": len(timeline["cues"])}


@app.delete("/api/songs/{song_id}")
def api_delete_song(request: Request, song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        _fail(request, 404, "api.song_not_found")
    if not delete_song(song_id):
        _fail(request, 404, "api.song_not_found")
    return {"ok": True, "song_id": song_id}


@app.post("/api/songs/{song_id}/retry")
def api_retry_song(request: Request, song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        _fail(request, 404, "api.song_not_found")
    if song.get("status") != "failed":
        _fail(request, 400, "api.retry_only_failed")
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
    request: Request,
    q: str = "",
    by: str = "all",
    letter: str = "",
    page: int | None = None,
    count: int = 12,
    after: str = "",
) -> dict:
    lang = request_lang(request)
    songs = prefer_native_library([
        localize_song(lang, with_media_flags(song) or song) for song in list_songs()
    ])
    if page is None and not q and not letter and not after:
        tagged = [{**song, "letter": song_letter(song)} for song in songs]
        return {"songs": tagged, "total": len(tagged)}
    return query_library(songs, q=q, by=by, letter=letter, page=page or 1, count=count, after=after)


@app.get("/api/songs/{song_id}")
def api_song(request: Request, song_id: str) -> dict:
    song = localize_song(request_lang(request), with_media_flags(get_song(song_id)))
    if not song:
        _fail(request, 404, "api.song_not_found")
    folder = MEDIA_DIR / song_id
    song["files"] = sorted(path.name for path in folder.iterdir()) if folder.exists() else []
    return song


@app.get("/api/songs/{song_id}/learn")
def api_learn(request: Request, song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        _fail(request, 404, "api.song_not_found")
    path = MEDIA_DIR / song_id / "lyrics.json"
    if not path.exists():
        _fail(request, 409, "api.no_lyrics")
    try:
        timeline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(request, 409, "api.lyrics_not_ready")
    try:
        timeline = normalize_timeline(timeline)
    except ValueError as exc:
        _fail(request, 409, "api.lyrics_not_ready")
    quiz = build_learn_quiz(timeline, song, lang=request_lang(request))
    if not quiz["lines"]:
        _fail(request, 409, "api.no_learn_lines")
    return quiz


@app.get("/api/rooms")
def api_my_room(request: Request) -> dict:
    code = room_for_hosts(_host_keys(request))
    if not code:
        return {"code": ""}
    return _room_view(code, lang=request_lang(request))


@app.post("/api/rooms")
def api_create_room(request: Request) -> JSONResponse:
    ua = request.headers.get("user-agent") or ""
    machine = _host_machine(request)
    token = machine if len(machine) >= 8 else store.new_id()
    room = ensure_room_for_host(host_keys(token, ua, _request_ip(request)), ua)
    response = JSONResponse(_room_view(room["code"], lang=request_lang(request)))
    return _set_host_cookie(response, request, token)


@app.get("/api/rooms/{code}")
def api_room(request: Request, code: str) -> JSONResponse:
    view = _room_view(code.upper(), lang=request_lang(request))
    token = _bind_host(request, view["code"])
    return _set_host_cookie(JSONResponse(view), request, token)


@app.post("/api/rooms/{code}/lan")
def api_room_lan(request: Request, code: str, payload: RoomLanPayload) -> JSONResponse:
    code = code.upper()
    try:
        snap = set_room_lan(code, payload.origin_url(), payload.mic_port, payload.mic_sample_rate)
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    token = _bind_host(request, snap["code"])
    return _set_host_cookie(JSONResponse(_room_view(code, snap, lang=request_lang(request))), request, token)


@app.post("/api/rooms/{code}/queue")
async def api_enqueue(request: Request, code: str, payload: RoomCommandPayload) -> dict:
    code = code.upper()
    song_id = str(payload.song_id or "")
    if not get_song(song_id):
        _fail(request, 404, "api.song_not_found")
    try:
        snap = _run_room_command(code, RoomCommand.from_payload("enqueue", payload.as_dict()))
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    view = _room_view(code, snap, lang=request_lang(request))
    await _broadcast(code, {"type": "snapshot", "room": view})
    return view


@app.post("/api/rooms/{code}/bump")
def api_bump(code: str, payload: RoomCommandPayload) -> dict:
    return _run_room_command(code, RoomCommand.from_payload("bump", payload.as_dict()))


@app.post("/api/rooms/{code}/skip")
async def api_skip(request: Request, code: str) -> dict:
    code = code.upper()
    view = _room_view(code, _run_room_command(code, RoomCommand.from_payload("skip")), lang=request_lang(request))
    await _broadcast(code, {"type": "snapshot", "room": view})
    return view


@app.post("/api/rooms/{code}/play")
async def api_play(request: Request, code: str, payload: RoomCommandPayload) -> dict:
    code = code.upper()
    try:
        snap = _run_room_command(code, RoomCommand.from_payload("play", payload.as_dict()))
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    view = _room_view(code, snap, lang=request_lang(request))
    await _broadcast(code, {"type": "snapshot", "room": view})
    return view


@app.post("/api/rooms/{code}/mix")
async def api_mix(request: Request, code: str, payload: RoomCommandPayload) -> dict:
    code = code.upper()
    snap = _run_room_command(code, RoomCommand.from_payload("mix", payload.as_dict()))
    view = _room_view(code, snap, lang=request_lang(request))
    await _broadcast(code, {"type": "snapshot", "room": view})
    return view


@app.websocket("/ws/rooms/{code}")
async def ws_room(ws: WebSocket, code: str) -> None:
    code = code.upper()
    lang = ws_lang(ws)
    await ws.accept()
    _rooms.setdefault(code, set()).add(ws)
    _peers[ws] = {"code": code, "peer": "", "role": ""}
    await ws.send_json({"type": "snapshot", "room": _room_view(code, lang=lang)})
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
                    await _broadcast(code, {"type": "snapshot", "room": _room_view(code, lang=lang)})
                continue
            if action == "mic":
                peer = str(msg.get("from") or _peers.get(ws, {}).get("peer") or "")
                if msg.get("on"):
                    if peer:
                        _mics[code] = peer
                elif _mics.get(code) == peer or not peer:
                    _mics.pop(code, None)
                if msg.get("mic_gain") is not None:
                    _run_room_command(
                        code,
                        RoomCommand.from_payload("mix", {"mic_gain": msg.get("mic_gain")}),
                    )
                await _broadcast(code, {"type": "snapshot", "room": _room_view(code, lang=lang)})
                continue
            if action == "skip":
                try:
                    event = normalize_playback_event(action, msg)
                    snap = _run_room_command(code, RoomCommand.from_payload(event["action"], event))
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": localize_error_text(lang, str(exc))})
                    continue
            elif action == "bump":
                try:
                    event = normalize_playback_event(action, msg)
                    snap = _run_room_command(code, RoomCommand.from_payload(event["action"], event))
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": localize_error_text(lang, str(exc))})
                    continue
            elif action == "enqueue":
                try:
                    snap = _run_room_command(code, RoomCommand.from_payload("enqueue", msg))
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": localize_error_text(lang, str(exc))})
                    continue
            elif action == "play":
                try:
                    event = normalize_playback_event(action, msg)
                    snap = _run_room_command(code, RoomCommand.from_payload(event["action"], event))
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": localize_error_text(lang, str(exc))})
                    continue
            elif action == "mix":
                snap = _run_room_command(code, RoomCommand.from_payload("mix", msg))
            else:
                await ws.send_json({"type": "error", "message": translate(lang, "api.unknown_command")})
                continue
            await _broadcast(code, {"type": "snapshot", "room": _room_view(code, snap, lang=lang)})
    except WebSocketDisconnect:
        info = _peers.pop(ws, {})
        _rooms.get(code, set()).discard(ws)
        peer = str(info.get("peer") or "")
        if peer and _mics.get(code) == peer:
            _mics.pop(code, None)
            await _broadcast(code, {"type": "rtc", "kind": "hangup", "from": peer})
            await _broadcast(code, {"type": "snapshot", "room": _room_view(code, lang=lang)})
        await _broadcast(
            code,
            {"type": "peer", "event": "leave", "peer": peer, "role": info.get("role") or ""},
        )


@app.get("/media/{song_id}/{name}")
def media(song_id: str, name: str, request: Request):
    root = MEDIA_DIR.resolve()
    path = (root / song_id / name).resolve()
    if root not in path.parents:
        raise HTTPException(404)
    rev = (request.query_params.get("v") or "").strip()
    cache = (
        "public, max-age=31536000, immutable"
        if rev
        else "no-cache, must-revalidate"
    )
    if path.exists():
        return FileResponse(
            path,
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": cache},
        )
    if oss_ready():
        url = public_url(song_id, name)
        if rev:
            url = f"{url}?v={quote(rev, safe='')}"
        return RedirectResponse(url, status_code=302)
    raise HTTPException(404)


@app.get("/m.html")
def mobile_page():
    path = WEB / "m.html"
    if not path.exists():
        raise HTTPException(404)
    return versioned_response(path, WEB)


@app.get("/login.html")
def login_page():
    path = WEB / "login.html"
    if not path.exists():
        raise HTTPException(404)
    return versioned_response(path, WEB)


if WEB.exists():
    app.mount("/", VersionedStaticFiles(directory=WEB, html=True), name="web")
