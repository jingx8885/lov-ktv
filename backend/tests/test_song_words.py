"""Song-scoped vocabulary: extraction, the global word table, and the API.

Sectioned like test_recite.py: pure worker functions, then storage, then the
HTTP round trip.
"""

import json
import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from lovktv.workers import srs

DAY = srs.DAY_MS


def _noon_today() -> int:
    """Noon UTC today. The store stamps new rows with the real clock, so a fixed
    historical timestamp would push every fresh word past the due cutoff."""
    day = datetime.fromtimestamp(time.time(), timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    return int(day.timestamp() * 1000)


NOW = _noon_today()

JA_TIMELINE = {
    "language": "ja",
    "cues": [
        {
            "text": "走る記憶",
            "zh": "奔跑的记忆",
            "start_ms": 1000,
            "end_ms": 3200,
            "tokens": [
                {"text": "走る", "zh": "奔跑", "romaji": "hashiru", "start_ms": 1000, "end_ms": 2000},
                {"text": "記憶", "zh": "记忆", "romaji": "kioku", "start_ms": 2000, "end_ms": 3200},
            ],
        },
        {
            "text": "青い空",
            "zh": "蓝色的天空",
            "start_ms": 4000,
            "end_ms": 6200,
            "tokens": [
                {"text": "青い", "zh": "蓝色", "romaji": "aoi", "start_ms": 4000, "end_ms": 5000},
                {"text": "空", "zh": "天空", "romaji": "sora", "start_ms": 5000, "end_ms": 6200},
            ],
        },
        {
            # A repeat of an earlier word plus a filler line's worth of noise.
            "text": "走る ラララ",
            "zh": "奔跑 啦啦啦",
            "start_ms": 7000,
            "end_ms": 9000,
            "tokens": [
                {"text": "走る", "zh": "奔跑", "romaji": "hashiru", "start_ms": 7000, "end_ms": 8000},
                {"text": "ラララ", "zh": "啦啦啦", "romaji": "rarara", "start_ms": 8000, "end_ms": 9000},
            ],
        },
    ],
}

OTHER_TIMELINE = {
    "language": "ja",
    "cues": [
        {
            "text": "空を見て",
            "zh": "看着天空",
            "start_ms": 500,
            "end_ms": 2500,
            "tokens": [
                {"text": "空", "zh": "天空", "romaji": "sora", "start_ms": 500, "end_ms": 1500},
                {"text": "見て", "zh": "看着", "romaji": "mite", "start_ms": 1500, "end_ms": 2500},
            ],
        }
    ],
}


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main
    from lovktv.core import config
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    # media_root() reads config, not store — without this the routers cannot
    # find the lyrics file the test just wrote.
    config.MEDIA_DIR = store.MEDIA_DIR
    store.init_db()
    return main, store


def _song(store, title, timeline, language="ja"):
    song = store.create_song(title, "", language)
    store.update_song(song["id"], status="ready")
    folder = store.MEDIA_DIR / song["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lyrics.json").write_text(
        json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
    )
    return song["id"]


# ------------------------------------------------------------ worker (pure)


def test_song_words_dedupes_and_drops_filler():
    from lovktv.workers.song_words import song_words

    words = song_words(JA_TIMELINE, {"language": "ja", "title": "群青"})
    texts = [word["text"] for word in words]
    # 走る appears in two lines but is one vocabulary item.
    assert texts.count("走る") == 1
    assert set(texts) == {"走る", "記憶", "青い", "空"}
    # "ラララ" is a vocalisation, not vocabulary.
    assert "ラララ" not in texts


def test_song_words_anchor_first_occurrence():
    from lovktv.workers.song_words import song_words

    words = {w["text"]: w for w in song_words(JA_TIMELINE, {"language": "ja"})}
    run = words["走る"]
    # The first sung occurrence, not the later repeat at 7000ms.
    assert run["start_ms"] == 1000
    assert run["end_ms"] == 2000
    assert run["line_text"] == "走る記憶"
    assert run["romaji"] == "hashiru"
    assert run["zh"] == "奔跑"
    assert run["word_id"]


def test_song_words_id_ignores_the_song():
    """The same word in two songs must hash to one id — that is what makes
    proficiency shared rather than duplicated per song."""
    from lovktv.workers.song_words import song_words

    first = {w["text"]: w["word_id"] for w in song_words(JA_TIMELINE, {"language": "ja"})}
    second = {w["text"]: w["word_id"] for w in song_words(OTHER_TIMELINE, {"language": "ja"})}
    assert first["空"] == second["空"]


def test_merge_state_and_summary():
    from lovktv.workers.song_words import merge_state, song_words, words_summary

    words = song_words(JA_TIMELINE, {"language": "ja"})
    saved = [
        {"word_id": words[0]["word_id"], "stage": 2, "reps": 3, "due_at": NOW, "retired_at": 0, "skipped_at": 0},
        {"word_id": words[1]["word_id"], "stage": 6, "reps": 9, "due_at": 0, "retired_at": NOW, "skipped_at": 0},
        {"word_id": words[2]["word_id"], "stage": 0, "reps": 0, "due_at": NOW, "retired_at": 0, "skipped_at": NOW},
    ]
    rows = merge_state(words, saved)
    assert rows[0]["known"] and rows[0]["stage"] == 2
    assert rows[1]["mastered"]
    assert rows[2]["skipped"]
    assert not rows[3]["known"]
    summary = words_summary(rows, NOW)
    assert summary["total"] == 4
    # Mastered and set-aside words leave the actionable pool.
    assert summary["kept"] == 2
    assert summary["mastered"] == 1
    assert summary["skipped"] == 1
    assert summary["due"] == 2


# ------------------------------------------------------------------- storage


def test_word_state_is_shared_across_songs(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import words as words_store

    wid = words_store.word_id("ja", "空")
    words_store.setup_song(
        "u:1", "songA", [{"language": "ja", "text": "空", "zh": "天空", "song_id": "songA"}], []
    )
    words_store.bump_word("u:1", wid, True, NOW)
    # Meeting the same word in a second song must not reset the box earned.
    words_store.setup_song(
        "u:1", "songB", [{"language": "ja", "text": "空", "zh": "天空", "song_id": "songB"}], []
    )
    saved = words_store.get_word("u:1", wid)
    assert saved["stage"] == 1
    assert saved["reps"] == 1
    assert words_store.count_words("u:1") == 1
    # But the word now belongs to both songs' scopes.
    assert wid in words_store.song_word_ids("u:1", "songA")
    assert wid in words_store.song_word_ids("u:1", "songB")


def test_skipping_is_global_and_restorable(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import words as words_store

    wid = words_store.word_id("ja", "空")
    words_store.setup_song("u:1", "songA", [], [{"language": "ja", "text": "空", "song_id": "songA"}])
    words_store.setup_song(
        "u:1", "songB", [{"language": "ja", "text": "空", "song_id": "songB"}], []
    )
    # songB kept it, so the explicit keep clears the flag.
    assert not words_store.get_word("u:1", wid)["skipped_at"]
    words_store.set_skipped("u:1", [wid], True)
    assert words_store.get_word("u:1", wid)["skipped_at"] > 0
    # Set aside means out of every song's queue, not just the one it was cut in.
    assert words_store.due_words("u:1", "songA", 10, NOW) == []
    assert words_store.due_words("u:1", "songB", 10, NOW) == []
    words_store.restore_word("u:1", wid)
    assert words_store.get_word("u:1", wid)["skipped_at"] == 0
    assert len(words_store.due_words("u:1", "songB", 10, NOW)) == 1


def test_setup_is_idempotent(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import words as words_store

    keep = [{"language": "ja", "text": "空", "zh": "天空", "song_id": "songA"}]
    words_store.setup_song("u:1", "songA", keep, [])
    wid = words_store.word_id("ja", "空")
    words_store.bump_word("u:1", wid, True, NOW)
    before = words_store.get_word("u:1", wid)
    words_store.setup_song("u:1", "songA", keep, [])
    after = words_store.get_word("u:1", wid)
    # A re-submitted confirm must not add a rep or move a box.
    assert (after["stage"], after["reps"], after["due_at"]) == (
        before["stage"],
        before["reps"],
        before["due_at"],
    )
    assert words_store.count_words("u:1") == 1


def test_mastered_word_leaves_the_queue_then_restores(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import words as words_store

    words_store.setup_song(
        "u:1", "songA", [{"language": "ja", "text": "空", "song_id": "songA"}], []
    )
    wid = words_store.word_id("ja", "空")
    for _ in range(srs.MAX_STAGE):
        words_store.bump_word("u:1", wid, True, NOW)
    saved = words_store.get_word("u:1", wid)
    assert saved["stage"] == srs.MAX_STAGE
    assert saved["retired_at"] > 0
    assert words_store.due_words("u:1", "songA", 10, NOW) == []
    # Restoring drops it a box and makes it due, otherwise "restore" would hand
    # back a word that still refuses to appear.
    restored = words_store.restore_word("u:1", wid)
    assert restored["retired_at"] == 0
    assert restored["stage"] == srs.MAX_STAGE - 1
    assert len(words_store.due_words("u:1", "songA", 10, NOW)) == 1


def test_a_miss_drops_the_box_and_comes_back_today(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import words as words_store

    words_store.setup_song(
        "u:1", "songA", [{"language": "ja", "text": "空", "song_id": "songA"}], []
    )
    wid = words_store.word_id("ja", "空")
    for _ in range(4):
        words_store.bump_word("u:1", wid, True, NOW)
    assert words_store.get_word("u:1", wid)["stage"] == 4
    missed = words_store.bump_word("u:1", wid, False, NOW)
    assert missed["stage"] == 2
    assert missed["lapses"] == 1
    assert missed["due_at"] <= srs.end_of_day(NOW)


def test_song_scope_isolates_words(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import words as words_store

    words_store.setup_song(
        "u:1", "songA", [{"language": "ja", "text": "記憶", "song_id": "songA"}], []
    )
    words_store.setup_song(
        "u:1", "songB", [{"language": "ja", "text": "見て", "song_id": "songB"}], []
    )
    a = [row["text"] for row in words_store.list_words("u:1", "songA")]
    b = [row["text"] for row in words_store.list_words("u:1", "songB")]
    assert a == ["記憶"]
    assert b == ["見て"]
    # No scope means the whole library.
    assert len(words_store.list_words("u:1")) == 2


def test_legacy_cards_merge_once_and_take_the_better_box(tmp_path, monkeypatch):
    _main, store = _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store
    from lovktv.storage import words as words_store

    # Real songs: the merge reads `language` off the songs row, and that is part
    # of the word id.
    song_a = _song(store, "A", JA_TIMELINE)
    song_b = _song(store, "B", OTHER_TIMELINE)
    # The same word collected in two songs is two legacy cards with two boxes.
    recite_store.upsert_card(
        "u:1",
        {"song_id": song_a, "song_title": "A", "item_key": f"{song_a}:空:1", "text": "空", "zh": "天空"},
    )
    recite_store.upsert_card(
        "u:1",
        {"song_id": song_b, "song_title": "B", "item_key": f"{song_b}:空:9", "text": "空", "zh": "天空"},
    )
    first = recite_store.card_id(song_a, f"{song_a}:空:1")
    for _ in range(3):
        recite_store.bump_card("u:1", first, True, NOW)

    result = words_store.migrate_cards("u:1")
    assert result["migrated"] is True
    assert result["words"] == 1
    wid = words_store.word_id("ja", "空")
    merged = words_store.get_word("u:1", wid)
    # The better of the two cards wins; a merge must never cost progress.
    assert merged["stage"] == 3
    assert merged["reps"] == 3
    assert merged["text"] == "空"
    # Both songs stay reachable as sources.
    assert wid in words_store.song_word_ids("u:1", song_a)
    assert wid in words_store.song_word_ids("u:1", song_b)
    # Second call is a no-op, and re-running cannot double-count.
    again = words_store.migrate_cards("u:1")
    assert again["migrated"] is False
    assert words_store.count_words("u:1") == 1


# ----------------------------------------------------------------------- api


def test_song_words_api_setup_then_review(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    song_id = _song(store, "群青", JA_TIMELINE)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        pack = client.get(f"/api/songs/{song_id}/learn/words", headers=head)
        assert pack.status_code == 200
        body = pack.json()
        assert body["first_setup"] is True
        assert body["total"] == 4
        # Nothing set aside yet, so the whole list reads as keepable.
        assert body["kept"] == 4
        assert body["skipped"] == 0
        assert all(not word["known"] for word in body["words"])
        ids = [word["word_id"] for word in body["words"]]

        # Keep three, cut one.
        saved = client.post(
            f"/api/songs/{song_id}/learn/words/setup",
            json={"keep": ids[:3], "skip": ids[3:]},
            headers=head,
        )
        assert saved.status_code == 200
        assert saved.json()["kept"] == 3
        assert saved.json()["skipped"] == 1
        assert saved.json()["first_setup"] is False

        # Re-opening now goes straight to review rather than the filter screen.
        again = client.get(f"/api/songs/{song_id}/learn/words", headers=head).json()
        assert again["first_setup"] is False
        assert again["kept"] == 3
        assert again["skipped"] == 1

        # A song-scoped round only offers this song's kept words.
        session = client.get(
            f"/api/learn/session?song_id={song_id}&size=20", headers=head
        ).json()
        assert session["song_id"] == song_id
        assert len(session["cards"]) == 3
        assert all(card["card_id"] in ids[:3] for card in session["cards"])

        graded = client.post(
            "/api/learn/session",
            json={
                "song_id": song_id,
                "answers": [{"card_id": ids[0], "ok": True}, {"card_id": ids[1], "ok": False}],
            },
            headers=head,
        )
        assert graded.status_code == 200
        assert graded.json()["graded"] == 2
        # One streak per deck: a song-scoped round is still the day's practice.
        assert graded.json()["deck"]["streak"] == 1
        assert graded.json()["deck"]["song_id"] == song_id


def test_setup_rejects_words_from_outside_the_song(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    song_id = _song(store, "群青", JA_TIMELINE)
    other = _song(store, "別の歌", OTHER_TIMELINE)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        mine = client.get(f"/api/songs/{song_id}/learn/words", headers=head).json()
        theirs = client.get(f"/api/songs/{other}/learn/words", headers=head).json()
        foreign = next(
            word["word_id"]
            for word in theirs["words"]
            if word["word_id"] not in {w["word_id"] for w in mine["words"]}
        )
        bad = client.post(
            f"/api/songs/{song_id}/learn/words/setup",
            json={"keep": [foreign], "skip": []},
            headers=head,
        )
        assert bad.status_code == 400
        # Malformed and empty payloads are rejected too.
        assert (
            client.post(
                f"/api/songs/{song_id}/learn/words/setup",
                json={"keep": "nope", "skip": []},
                headers=head,
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/songs/{song_id}/learn/words/setup",
                json={"keep": [], "skip": []},
                headers=head,
            ).status_code
            == 400
        )
        # A duplicated id across keep and skip is contradictory, not a merge.
        dupe = mine["words"][0]["word_id"]
        assert (
            client.post(
                f"/api/songs/{song_id}/learn/words/setup",
                json={"keep": [dupe], "skip": [dupe]},
                headers=head,
            ).status_code
            == 400
        )


def test_session_rejects_a_word_the_song_does_not_own(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    song_id = _song(store, "群青", JA_TIMELINE)
    other = _song(store, "別の歌", OTHER_TIMELINE)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        mine = client.get(f"/api/songs/{song_id}/learn/words", headers=head).json()
        theirs = client.get(f"/api/songs/{other}/learn/words", headers=head).json()
        client.post(
            f"/api/songs/{song_id}/learn/words/setup",
            json={"keep": [w["word_id"] for w in mine["words"]], "skip": []},
            headers=head,
        )
        outsider = next(
            word["word_id"]
            for word in theirs["words"]
            if word["word_id"] not in {w["word_id"] for w in mine["words"]}
        )
        forged = client.post(
            "/api/learn/session",
            json={"song_id": song_id, "answers": [{"card_id": outsider, "ok": True}]},
            headers=head,
        )
        assert forged.status_code == 400


def test_song_review_finishes_when_everything_is_mastered(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    song_id = _song(store, "群青", JA_TIMELINE)
    from lovktv.storage import words as words_store

    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        pack = client.get(f"/api/songs/{song_id}/learn/words", headers=head).json()
        ids = [word["word_id"] for word in pack["words"]]
        client.post(
            f"/api/songs/{song_id}/learn/words/setup",
            json={"keep": ids, "skip": []},
            headers=head,
        )
        for wid in ids:
            for _ in range(srs.MAX_STAGE):
                words_store.bump_word("m:deviceone", wid, True, NOW)
        # Nothing due is a 409 the phone renders as a finished state, not an error.
        assert (
            client.get(f"/api/learn/session?song_id={song_id}", headers=head).status_code
            == 409
        )
        deck = client.get(f"/api/learn/deck?song_id={song_id}", headers=head).json()
        assert deck["mastered"] == len(ids)
        assert deck["due"] == 0


def test_song_without_glossed_words_is_a_409(tmp_path, monkeypatch):
    main, store = _boot(tmp_path, monkeypatch)
    bare = {
        "language": "ja",
        "cues": [
            {"text": "ラララ", "zh": "啦啦啦", "start_ms": 0, "end_ms": 900, "tokens": []}
        ],
    }
    song_id = _song(store, "無言", bare)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        res = client.get(f"/api/songs/{song_id}/learn/words", headers=head)
        assert res.status_code == 409


def test_lyrics_tap_and_song_setup_share_one_word(tmp_path, monkeypatch):
    """The collected-words deck and the song deck are one word library: a word
    tapped in the lyrics view is the same row the song's review schedules."""
    main, store = _boot(tmp_path, monkeypatch)
    song_id = _song(store, "群青", JA_TIMELINE)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        added = client.post(
            "/api/learn/cards",
            json={"song_id": song_id, "song_title": "群青", "text": "空", "zh": "天空"},
            headers=head,
        )
        assert added.status_code == 200
        wid = added.json()["card"]["card_id"]
        client.post(
            "/api/learn/session",
            json={"answers": [{"card_id": wid, "ok": True}]},
            headers=head,
        )
        pack = client.get(f"/api/songs/{song_id}/learn/words", headers=head).json()
        row = next(word for word in pack["words"] if word["word_id"] == wid)
        # The song's list shows the progress already made from the lyrics page.
        assert row["known"] is True
        assert row["stage"] == 1
        assert client.get("/api/learn/deck", headers=head).json()["total"] == 1
