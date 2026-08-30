"""Song campaign, lesson, and mistake-notebook APIs."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body
from starlette.requests import Request

from lovktv.domain.timeline import normalize_timeline
from lovktv.identity.quota import guest_key
from lovktv.locale.i18n import request_lang
from lovktv.platform.runtime import media_root
from lovktv.services.http import current_user, fail
from lovktv.storage import learn as learn_store
from lovktv.storage.store import get_song
from lovktv.workers.campaign import (
    PASS_PCT,
    SKILLS,
    apply_lesson_result,
    build_campaign,
    build_lesson,
    build_review_lesson,
    singable_cues,
)
from lovktv.workers.learn import build_learn_quiz

router = APIRouter()


def learn_owner(request: Request) -> str:
    user = current_user(request)
    if user and user.get("id"):
        return "u:" + str(user["id"])
    return guest_key(request, user)


def load_song_timeline(request: Request, song_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
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
    if not singable_cues(timeline):
        fail(request, 409, "api.no_learn_lines")
    return song, timeline


@router.get("/api/songs/{song_id}/learn/campaign")
def api_learn_campaign(request: Request, song_id: str) -> dict:
    song, timeline = load_song_timeline(request, song_id)
    owner = learn_owner(request)
    return build_campaign(
        timeline,
        song,
        progress=learn_store.list_progress(owner, song_id),
        mastery=learn_store.list_mastery(owner, song_id),
        mistakes=len(learn_store.list_mistakes(owner, song_id, open_only=True)),
        lang=request_lang(request),
    )


@router.get("/api/songs/{song_id}/learn/lesson")
def api_learn_lesson(
    request: Request, song_id: str, unit: str = "u0", skill: str = "word"
) -> dict:
    if skill not in SKILLS:
        fail(request, 400, "api.bad_skill")
    song, timeline = load_song_timeline(request, song_id)
    lesson = build_lesson(timeline, song, unit, skill, lang=request_lang(request))
    if not lesson:
        fail(request, 400, "api.bad_unit")
    if not lesson.get("play_mode") and not lesson.get("items"):
        fail(request, 409, "api.no_learn_lines")
    return lesson


@router.post("/api/songs/{song_id}/learn/lesson")
def api_learn_lesson_submit(
    request: Request, song_id: str, body: dict = Body(default_factory=dict)
) -> dict:
    song, timeline = load_song_timeline(request, song_id)
    owner = learn_owner(request)
    unit_id = str(body.get("unit_id") or body.get("unit") or "u0")
    skill = str(body.get("skill") or "")
    if skill not in SKILLS and skill != "review":
        fail(request, 400, "api.bad_skill")
    answers = body.get("answers") if isinstance(body.get("answers"), list) else []
    try:
        pct = int(body.get("pct") or 0)
    except (TypeError, ValueError):
        pct = 0
    result = apply_lesson_result(
        owner, song_id, unit_id, skill, pct=pct, answers=answers
    )
    campaign = build_campaign(
        timeline,
        song,
        progress=learn_store.list_progress(owner, song_id),
        mastery=learn_store.list_mastery(owner, song_id),
        mistakes=result["mistakes"],
        lang=request_lang(request),
    )
    return {**result, "campaign": campaign, "pass_pct": PASS_PCT}


@router.get("/api/songs/{song_id}/learn/mistakes")
def api_learn_mistakes(request: Request, song_id: str) -> dict:
    song, timeline = load_song_timeline(request, song_id)
    owner = learn_owner(request)
    rows = learn_store.list_mistakes(owner, song_id, open_only=True)
    quiz = build_learn_quiz(timeline, song, lang=request_lang(request))
    return {
        "song_id": song_id,
        "title": song.get("title") or quiz.get("title") or "",
        "mistakes": [
            {
                "qkind": row.get("qkind"),
                "item_key": row.get("item_key"),
                "prompt": row.get("prompt"),
                "stem": row.get("stem"),
                "answer_text": row.get("answer_text"),
                "wrong_count": int(row.get("wrong_count") or 0),
                "correct_streak": int(row.get("correct_streak") or 0),
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.get("/api/songs/{song_id}/learn/review")
def api_learn_review(request: Request, song_id: str) -> dict:
    song, timeline = load_song_timeline(request, song_id)
    owner = learn_owner(request)
    rows = learn_store.list_mistakes(owner, song_id, open_only=True)
    if not rows:
        fail(request, 409, "api.no_mistakes")
    return build_review_lesson(timeline, song, rows, lang=request_lang(request))


@router.post("/api/songs/{song_id}/learn/review")
def api_learn_review_submit(
    request: Request, song_id: str, body: dict = Body(default_factory=dict)
) -> dict:
    payload = dict(body or {})
    payload["unit_id"] = "review"
    payload["skill"] = "review"
    return api_learn_lesson_submit(request, song_id, payload)
