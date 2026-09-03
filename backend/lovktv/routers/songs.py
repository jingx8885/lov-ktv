from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from starlette.requests import Request

from lovktv.agents.ja_lyrics import annotate_ja_lines
from lovktv.catalog.audio import (
    is_preview_id,
    open_preview_stream,
    resolve_audio_source,
)
from lovktv.catalog.index import (
    library_sort_key,
    prefer_native_library,
    query_library,
    song_letter,
)
from lovktv.catalog.mugen import is_mugen_kid
from lovktv.catalog.search import search_songs
from lovktv.domain.timeline import normalize_timeline
from lovktv.identity.points import charge_process
from lovktv.identity.quota import learn_owner
from lovktv.identity.song_admin import is_song_admin
from lovktv.locale.i18n import localize_exc, localize_song, request_lang
from lovktv.locale.i18n import t as i18n_t
from lovktv.pipeline.lyrics import validate_timeline, write_manual_lrc, write_subtitles
from lovktv.platform.runtime import media_root
from lovktv.services.http import fail
from lovktv.services.http import current_user
from lovktv.storage.store import (
    create_song,
    delete_song,
    get_song,
    list_songs,
    retry_query,
    update_song,
    with_media_flags,
)
from lovktv.storage import favorites as favorite_store
from lovktv.workers.jobs import process_import, process_realign, process_upload, spawn
from lovktv.workers.learn import build_learn_quiz

router = APIRouter()


@router.get("/api/search")
def api_search(request: Request, q: str, count: int = 10, page: int = 1) -> dict:
    if not q.strip():
        fail(request, 400, "api.missing_q")
    try:
        return search_songs(q.strip(), count=count, page=page)
    except Exception as exc:
        fail(request, 502, "api.search_failed", exc=exc)


@router.get("/api/preview/{song_id}/resolve")
def api_preview_resolve(
    request: Request, song_id: str, title: str = "", artist: str = "", media: str = ""
) -> dict:
    if is_mugen_kid(song_id):
        return {"ok": True, "id": song_id, "kind": "mugen", "title": title}
    if not is_preview_id(song_id):
        fail(request, 400, "api.bad_preview_id")
    source = resolve_audio_source(song_id, title, artist)
    if not source:
        fail(request, 404, "api.preview_unavailable")
    return {
        "ok": True,
        "id": song_id,
        "kind": source.get("kind"),
        "title": source.get("title") or title,
    }


@router.get("/api/preview/{song_id}")
def api_preview(
    request: Request, song_id: str, title: str = "", artist: str = "", media: str = ""
):
    if not is_preview_id(song_id):
        fail(request, 400, "api.bad_preview_id")
    resp, source = open_preview_stream(song_id, title, artist, media=media)
    if resp is None:
        fail(request, 404, "api.preview_unavailable")
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

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        chunks(), media_type=ctype, headers={"Cache-Control": "no-store"}
    )


@router.post("/api/songs/import")
def api_import(request: Request, payload: dict) -> dict:
    query = str(payload.get("query") or payload.get("title") or "").strip()
    if not query:
        fail(request, 400, "api.missing_query")
    charge_process(request)
    raw_id = str(payload.get("id") or "")
    language = str(payload.get("language") or ("ja" if is_mugen_kid(raw_id) else "zh"))
    song = create_song(
        title=str(payload.get("title") or query),
        artist=str(payload.get("artist") or ""),
        language=language,
        netease_id=raw_id,
    )
    # Importing from the song-picker is also the user's explicit save action.
    favorite_store.set_favorite(learn_owner(request), song["id"], True)
    song["favorite"] = True
    spawn(process_import, song["id"], query, raw_id, language)
    return song


@router.post("/api/songs")
async def api_upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(""),
    language: str = Form("zh"),
    lyrics: str = Form(""),
    request: Request = None,
) -> dict:
    charge_process(request)
    song = create_song(
        title or file.filename or i18n_t(request, "api.unnamed"), artist, language
    )
    favorite_store.set_favorite(learn_owner(request), song["id"], True)
    song["favorite"] = True
    dest = media_root() / song["id"] / "original.mp3"
    with dest.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    if lyrics.strip():
        (media_root() / song["id"] / "lyrics.lrc").write_text(lyrics, encoding="utf-8")
    spawn(process_upload, song["id"], dest, language)
    return song


@router.post("/api/agents/ja-lyrics")
def api_ja_lyrics(request: Request, payload: dict = Body(default={})) -> dict:
    lines = [str(item) for item in (payload.get("lines") or []) if str(item).strip()]
    if not lines:
        fail(request, 400, "api.missing_lines")
    try:
        return annotate_ja_lines(
            lines,
            title=str(payload.get("title") or ""),
            artist=str(payload.get("artist") or ""),
        )
    except Exception as exc:
        fail(request, 502, "api.ja_annotate_failed", exc=exc)


@router.post("/api/songs/{song_id}/realign")
def api_realign(
    request: Request, song_id: str, payload: dict = Body(default={})
) -> dict:
    if not is_song_admin(current_user(request)):
        fail(request, 403, "api.song_admin_required")
    song = get_song(song_id)
    if not song:
        fail(request, 404, "api.song_not_found")
    # Mark the song before queuing so clients do not observe the old ready
    # state and report completion before the worker has started.
    update_song(song_id, status="aligning", error="")
    args = (
        process_realign,
        song_id,
        payload.get("language") or song.get("language"),
        bool(payload.get("rebuild_mtv")),
    )
    if payload.get("force"):
        spawn(*args, force=True)
    else:
        spawn(*args)
    return {"ok": True, "song_id": song_id, "status": "aligning"}


@router.put("/api/songs/{song_id}/lyrics")
def api_save_lyrics(
    request: Request, song_id: str, payload: dict = Body(default={})
) -> dict:
    song = get_song(song_id)
    if not song:
        fail(request, 404, "api.song_not_found")
    try:
        timeline = validate_timeline(payload)
    except ValueError as exc:
        raise HTTPException(400, localize_exc(request, exc)) from exc
    write_subtitles(timeline, media_root() / song_id)
    write_manual_lrc(media_root() / song_id, timeline["cues"])
    return {"ok": True, "song_id": song_id, "cues": len(timeline["cues"])}


@router.delete("/api/songs/{song_id}")
def api_delete_song(request: Request, song_id: str) -> dict:
    if not get_song(song_id) or not delete_song(song_id):
        fail(request, 404, "api.song_not_found")
    return {"ok": True, "song_id": song_id}


@router.post("/api/songs/{song_id}/favorite")
def api_favorite_song(request: Request, song_id: str, payload: dict = Body(default={})) -> dict:
    if not get_song(song_id):
        fail(request, 404, "api.song_not_found")
    favorite = payload.get("favorite")
    if favorite is None:
        favorite = not favorite_store.is_favorite(learn_owner(request), song_id)
    favorite = bool(favorite)
    favorite_store.set_favorite(learn_owner(request), song_id, favorite)
    return {"ok": True, "song_id": song_id, "favorite": favorite}


@router.get("/api/songs/{song_id}/favorite")
def api_song_favorite(request: Request, song_id: str) -> dict:
    if not get_song(song_id):
        fail(request, 404, "api.song_not_found")
    return {
        "ok": True,
        "song_id": song_id,
        "favorite": favorite_store.is_favorite(learn_owner(request), song_id),
    }


@router.delete("/api/songs/{song_id}/favorite")
def api_unfavorite_song(request: Request, song_id: str) -> dict:
    if not get_song(song_id):
        fail(request, 404, "api.song_not_found")
    favorite_store.set_favorite(learn_owner(request), song_id, False)
    return {"ok": True, "song_id": song_id, "favorite": False}


@router.post("/api/songs/{song_id}/retry")
def api_retry_song(request: Request, song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        fail(request, 404, "api.song_not_found")
    if song.get("status") != "failed":
        fail(request, 400, "api.retry_only_failed")
    update_song(song_id, status="queued", error="")
    spawn(
        process_import,
        song_id,
        retry_query(song),
        str(song.get("netease_id") or ""),
        song.get("language"),
    )
    return {"ok": True, "song_id": song_id, "status": "queued"}


@router.get("/api/songs")
def api_songs(
    request: Request,
    q: str = "",
    by: str = "all",
    letter: str = "",
    page: int | None = None,
    count: int = 12,
    after: str = "",
    favorites_only: bool = False,
    favorites: bool = False,
) -> dict:
    lang = request_lang(request)
    owner = learn_owner(request)
    favorite_ids = favorite_store.list_favorite_ids(owner)
    can_realign = is_song_admin(current_user(request))
    raw_songs = [
        {
            **(localize_song(lang, with_media_flags(song) or song) or song),
            "can_realign": can_realign,
        }
        for song in list_songs()
    ]
    # Do not hide a user's explicitly saved composed copy merely because an
    # official-MV duplicate exists in the shared catalogue.
    songs = (
        raw_songs
        if (favorites_only or favorites)
        else prefer_native_library(raw_songs)
    )
    for song in songs:
        song["favorite"] = song.get("id") in favorite_ids
    if favorites_only or favorites:
        songs = [
            song
            for song in songs
            if song.get("favorite") and song.get("status") == "ready"
        ]
    if page is None and not q and not letter and not after:
        tagged = [{**song, "letter": song_letter(song)} for song in songs]
        tagged.sort(key=library_sort_key)
        return {"songs": tagged, "total": len(tagged)}
    return query_library(
        songs, q=q, by=by, letter=letter, page=page or 1, count=count, after=after
    )


@router.get("/api/songs/{song_id}")
def api_song(request: Request, song_id: str) -> dict:
    song = localize_song(request_lang(request), with_media_flags(get_song(song_id)))
    if not song:
        fail(request, 404, "api.song_not_found")
    folder = media_root() / song_id
    song["can_realign"] = is_song_admin(current_user(request))
    song["favorite"] = favorite_store.is_favorite(learn_owner(request), song_id)
    song["files"] = (
        sorted(path.name for path in folder.iterdir()) if folder.exists() else []
    )
    return song


@router.get("/api/songs/{song_id}/learn")
def api_learn(request: Request, song_id: str) -> dict:
    song = get_song(song_id)
    if not song:
        fail(request, 404, "api.song_not_found")
    path = media_root() / song_id / "lyrics.json"
    if not path.exists():
        fail(request, 409, "api.no_lyrics")
    try:
        timeline = normalize_timeline(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        fail(request, 409, "api.lyrics_not_ready")
    quiz = build_learn_quiz(timeline, song, lang=request_lang(request))
    if not quiz["lines"]:
        fail(request, 409, "api.no_learn_lines")
    return quiz
