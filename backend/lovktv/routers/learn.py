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


def _lesson_access(
    request: Request,
    song_id: str,
    unit_id: str,
    skill: str,
    *,
    allow_review: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    song, timeline = load_song_timeline(request, song_id)
    owner = learn_owner(request)
    if allow_review and skill == "review":
        rows = learn_store.list_mistakes(owner, song_id, open_only=True)
        if not rows:
            fail(request, 409, "api.no_mistakes")
        return song, timeline, build_review_lesson(timeline, song, rows, lang=request_lang(request))
    lesson = build_lesson(timeline, song, unit_id, skill, lang=request_lang(request))
    if not lesson:
        fail(request, 400, "api.bad_unit")
    campaign = build_campaign(
        timeline,
        song,
        progress=learn_store.list_progress(owner, song_id),
        mastery=learn_store.list_mastery(owner, song_id),
        mistakes=len(learn_store.list_mistakes(owner, song_id, open_only=True)),
        lang=request_lang(request),
    )
    node = next(
        (
            item
            for unit in campaign.get("units") or []
            if unit.get("id") == unit_id
            for item in unit.get("skills") or []
            if item.get("id") == skill
        ),
        None,
    )
    if not node:
        fail(request, 400, "api.bad_unit")
    if node.get("status") == "locked":
        fail(request, 403, "api.learn_locked")
    if not lesson.get("play_mode") and not lesson.get("items"):
        fail(request, 409, "api.no_learn_lines")
    return song, timeline, lesson


def _validated_answers(
    request: Request, lesson: dict[str, Any], answers: Any, *, strict: bool = True
) -> list[dict[str, Any]]:
    expected = {str(item.get("id")): item for item in lesson.get("items") or []}
    if not expected or not isinstance(answers, list) or not answers:
        fail(request, 400, "api.learn_invalid_submission")
    if strict and len(answers) != len(expected):
        fail(request, 400, "api.learn_invalid_submission")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in answers:
        if not isinstance(raw, dict):
            fail(request, 400, "api.learn_invalid_submission")
        item_id = str(raw.get("id") or "")
        if not item_id and not strict:
            raw_key = str(raw.get("key") or (raw.get("knowledge") or {}).get("key") or "")
            item_id = next(
                (
                    key
                    for key, candidate in expected.items()
                    if raw_key
                    and raw_key
                    in {
                        str((candidate.get("knowledge") or {}).get("key") or ""),
                        str(candidate.get("stem") or ""),
                    }
                ),
                "",
            )
        item = expected.get(item_id)
        if not item or item_id in seen:
            fail(request, 400, "api.learn_invalid_submission")
        seen.add(item_id)
        checked = dict(raw)
        if item.get("kind") == "match":
            pairs = {int(pair.get("id")) for pair in item.get("pairs") or []}
            matched = raw.get("matched_ids")
            misses = raw.get("match_misses")
            if not isinstance(matched, list) or not isinstance(misses, int):
                if strict or "ok" not in raw:
                    fail(request, 400, "api.learn_invalid_submission")
                checked["ok"] = bool(raw.get("ok"))
            else:
                try:
                    matched_set = {int(value) for value in matched}
                except (TypeError, ValueError):
                    fail(request, 400, "api.learn_invalid_submission")
                checked["ok"] = not misses and matched_set == pairs
        else:
            if raw.get("picked") is None and not strict:
                if "ok" not in raw:
                    fail(request, 400, "api.learn_invalid_submission")
                checked["ok"] = bool(raw.get("ok"))
            else:
                try:
                    picked = int(raw.get("picked"))
                except (TypeError, ValueError):
                    fail(request, 400, "api.learn_invalid_submission")
                choices = item.get("choices") or []
                valid_ids = {int(choice.get("id")) for choice in choices}
                if picked not in valid_ids:
                    fail(request, 400, "api.learn_invalid_submission")
                checked["ok"] = picked == int(item.get("answer"))
        knowledge = item.get("knowledge") if isinstance(item.get("knowledge"), dict) else {}
        checked["qkind"] = item.get("kind") or "word"
        checked["key"] = knowledge.get("key") or item.get("stem") or ""
        checked["knowledge"] = knowledge
        checked["prompt"] = item.get("prompt") or ""
        checked["stem"] = item.get("stem") or ""
        checked["answer_text"] = item.get("answer_text") or ""
        checked["payload"] = item
        out.append(checked)
    if strict and seen != set(expected):
        fail(request, 400, "api.learn_invalid_submission")
    return out


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
    _song, _timeline, lesson = _lesson_access(request, song_id, unit, skill)
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
    attempt_id = str(body.get("attempt_id") or "").strip()
    if attempt_id and not learn_store.claim_submission(owner, song_id, attempt_id):
        fail(request, 409, "api.learn_duplicate_submission")
    try:
        pct = int(body.get("pct"))
    except (TypeError, ValueError):
        fail(request, 400, "api.learn_invalid_submission")
    if pct < 0 or pct > 100:
        fail(request, 400, "api.learn_invalid_submission")
    if skill == "review":
        rows = learn_store.list_mistakes(owner, song_id, open_only=True)
        if not rows:
            fail(request, 409, "api.no_mistakes")
        lesson = build_review_lesson(timeline, song, rows, lang=request_lang(request))
    else:
        _song, _timeline, lesson = _lesson_access(request, song_id, unit_id, skill)
    raw_answers = body.get("answers")
    answers = (
        _validated_answers(request, lesson, raw_answers, strict=bool(attempt_id))
        if not lesson.get("play_mode")
        else []
    )
    if not lesson.get("play_mode"):
        total = len(answers)
        pct = round(sum(1 for item in answers if item.get("ok")) * 100 / total) if total else 0
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
