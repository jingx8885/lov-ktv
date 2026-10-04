"""Named per-owner playlists for the listen page, mirroring song favorites."""

from __future__ import annotations

from fastapi import APIRouter, Body
from starlette.requests import Request

from lovktv.catalog.index import song_letter
from lovktv.identity.quota import learn_owner
from lovktv.locale.i18n import localize_song, request_lang
from lovktv.services.http import fail
from lovktv.storage import favorites as favorite_store
from lovktv.storage import playlists as playlist_store
from lovktv.storage.store import get_song, list_songs, with_media_flags

router = APIRouter()


def _clean_name(payload: dict) -> str:
    return " ".join(str((payload or {}).get("name") or "").split())[: playlist_store.NAME_MAX]


def _song_payload(request: Request, row: dict, favorite_ids: set[str]) -> dict:
    lang = request_lang(request)
    song = with_media_flags(row) or row
    song = localize_song(lang, song) or song
    song["letter"] = song_letter(song)
    song["favorite"] = str(song.get("id") or "") in favorite_ids
    return song


@router.get("/api/playlists")
def api_playlists(request: Request, song_id: str = "") -> dict:
    owner = learn_owner(request)
    return {"playlists": playlist_store.list_playlists(owner, song_id)}


@router.post("/api/playlists")
def api_create_playlist(request: Request, payload: dict = Body(default={})) -> dict:
    owner = learn_owner(request)
    name = _clean_name(payload)
    if not name:
        fail(request, 400, "api.playlist_name")
    if playlist_store.playlist_count(owner) >= playlist_store.LIST_MAX:
        fail(request, 400, "api.playlist_full")
    if playlist_store.name_taken(owner, name):
        fail(request, 409, "api.playlist_dup")
    playlist = playlist_store.create_playlist(owner, name)
    return {"ok": True, "playlist": playlist}


@router.patch("/api/playlists/{playlist_id}")
def api_rename_playlist(
    request: Request, playlist_id: str, payload: dict = Body(default={})
) -> dict:
    owner = learn_owner(request)
    playlist = playlist_store.get_playlist(owner, playlist_id)
    if not playlist:
        fail(request, 404, "api.playlist_not_found")
    name = _clean_name(payload)
    if not name:
        fail(request, 400, "api.playlist_name")
    if playlist_store.name_taken(owner, name, exclude_id=playlist["id"]):
        fail(request, 409, "api.playlist_dup")
    playlist_store.rename_playlist(owner, playlist["id"], name)
    playlist["name"] = name
    return {"ok": True, "playlist": playlist}


@router.delete("/api/playlists/{playlist_id}")
def api_delete_playlist(request: Request, playlist_id: str) -> dict:
    owner = learn_owner(request)
    if not playlist_store.delete_playlist(owner, playlist_id):
        fail(request, 404, "api.playlist_not_found")
    return {"ok": True, "playlist_id": playlist_id}


@router.get("/api/playlists/{playlist_id}/songs")
def api_playlist_songs(request: Request, playlist_id: str) -> dict:
    owner = learn_owner(request)
    playlist = playlist_store.get_playlist(owner, playlist_id)
    if not playlist:
        fail(request, 404, "api.playlist_not_found")
    ids = playlist_store.playlist_song_ids(playlist["id"])
    favorite_ids = favorite_store.list_favorite_ids(owner)
    # Library order is irrelevant inside a list: keep the member order and
    # drop songs that no longer resolve (deleted while this call was live).
    known = {str(song.get("id")): song for song in list_songs()}
    songs = [
        _song_payload(request, known[song_id], favorite_ids)
        for song_id in ids
        if song_id in known
    ]
    return {"playlist": playlist, "songs": songs, "total": len(songs)}


@router.post("/api/playlists/{playlist_id}/songs")
def api_playlist_add(
    request: Request, playlist_id: str, payload: dict = Body(default={})
) -> dict:
    owner = learn_owner(request)
    playlist = playlist_store.get_playlist(owner, playlist_id)
    if not playlist:
        fail(request, 404, "api.playlist_not_found")
    song_id = str((payload or {}).get("song_id") or "").strip()
    if not get_song(song_id):
        fail(request, 404, "api.song_not_found")
    playlist_store.add_song(owner, playlist["id"], song_id)
    playlist = playlist_store.get_playlist(owner, playlist["id"]) or playlist
    return {"ok": True, "playlist": playlist, "song_id": song_id}


@router.delete("/api/playlists/{playlist_id}/songs/{song_id}")
def api_playlist_remove(request: Request, playlist_id: str, song_id: str) -> dict:
    owner = learn_owner(request)
    if not playlist_store.remove_song(owner, playlist_id, song_id):
        fail(request, 404, "api.playlist_song_missing")
    playlist = playlist_store.get_playlist(owner, playlist_id) or {"id": playlist_id}
    return {"ok": True, "playlist": playlist, "song_id": song_id}
