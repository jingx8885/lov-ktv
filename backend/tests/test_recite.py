"""Recitation decks: the SRS engine, the two stores, and the API round trip."""

import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from lovktv.workers import recite as recite_worker
from lovktv.workers import srs

DAY = srs.DAY_MS


def _noon_today() -> int:
    """Noon UTC today. The stores stamp new rows with the real clock, so a fixed
    historical timestamp would put every fresh card past the due cutoff; midday
    keeps the day arithmetic aligned and off the midnight boundary."""
    day = datetime.fromtimestamp(time.time(), timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    return int(day.timestamp() * 1000)


NOW = _noon_today()


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    from lovktv import main
    from lovktv.storage import store

    store.DB_PATH = tmp_path / "t.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    return main, store


def _card(text="なみだ", zh="眼泪", **over):
    card = {
        "song_id": "s1",
        "song_title": "夜空中最亮的星",
        "item_key": f"s1:{text}:1000",
        "text": text,
        "zh": zh,
        "romaji": "namida",
        "line_text": f"{text} が こぼれる",
        "start_ms": 1000,
        "end_ms": 2200,
    }
    card.update(over)
    return card


# ---------------------------------------------------------------- srs (pure)


def test_schedule_walks_the_boxes_and_retires():
    plan = srs.schedule(0, True, NOW)
    assert plan["stage"] == 1
    assert plan["due_at"] == NOW + 1 * DAY
    assert plan["retired_at"] == 0
    assert srs.schedule(3, True, NOW)["due_at"] == NOW + 8 * DAY
    # Clearing the last box retires the card: no due date, never queued again.
    retired = srs.schedule(srs.MAX_STAGE - 1, True, NOW)
    assert retired["stage"] == srs.MAX_STAGE
    assert retired["due_at"] == 0
    assert retired["retired_at"] == NOW
    assert srs.is_retired(retired["stage"])


def test_a_miss_drops_two_boxes_and_comes_back_today():
    missed = srs.schedule(4, False, NOW)
    assert missed["stage"] == 2
    # Straight back into today's queue — the interval box 2 would normally buy
    # is not earned by a word the user just failed to recall.
    assert missed["due_at"] == NOW
    assert missed["due_at"] <= srs.end_of_day(NOW)
    assert missed["retired_at"] == 0
    # From the bottom boxes a miss cannot go below zero.
    floor = srs.schedule(1, False, NOW)
    assert floor["stage"] == 0
    assert floor["due_at"] == NOW


def test_streak_counts_back_from_today_or_yesterday():
    today = srs.day_key(NOW)
    yesterday = srs.day_key(NOW - DAY)
    before = srs.day_key(NOW - 2 * DAY)
    assert srs.streak_from_days([today, yesterday, before], today) == 3
    # Nothing done yet today still reads as a live streak — it only breaks once
    # yesterday is missed too, otherwise the counter would zero out every dawn.
    assert srs.streak_from_days([yesterday, before], today) == 2
    assert srs.streak_from_days([before], today) == 0
    assert srs.streak_from_days([], today) == 0


# ------------------------------------------------------------------- storage


def test_upsert_card_is_idempotent_and_keeps_progress(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    first = recite_store.upsert_card("u:1", _card())
    assert first["card_id"] == recite_store.card_id("s1", "s1:なみだ:1000")
    recite_store.bump_card("u:1", first["card_id"], True, NOW)
    # Re-collecting the same word refreshes the wording but must not reset the
    # box the user already earned on it.
    again = recite_store.upsert_card("u:1", _card(zh="泪水"))
    assert again["card_id"] == first["card_id"]
    assert again["zh"] == "泪水"
    assert again["stage"] == 1
    assert again["reps"] == 1
    assert recite_store.count_cards("u:1") == 1


def test_import_does_not_fork_duplicates(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    batch = [_card(), _card(text="そら", zh="天空"), "junk", None]
    first = recite_store.import_cards("u:1", batch)
    assert first == {"seen": 2, "added": 2, "total": 2}
    second = recite_store.import_cards("u:1", batch)
    assert second == {"seen": 2, "added": 0, "total": 2}


def test_a_full_deck_refuses_new_cards(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    monkeypatch.setattr(recite_store, "MAX_CARDS", 1)
    assert recite_store.upsert_card("u:1", _card())
    assert recite_store.upsert_card("u:1", _card(text="そら", zh="天空")) == {}
    # The one already there stays editable — the cap only blocks new rows.
    assert recite_store.upsert_card("u:1", _card(zh="泪水"))["zh"] == "泪水"


def test_owners_never_see_each_others_cards(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    recite_store.upsert_card("u:7", _card())
    recite_store.upsert_card("m:devicetwo", _card(text="そら", zh="天空"))
    assert [row["text"] for row in recite_store.list_cards("u:7")] == ["なみだ"]
    assert [row["text"] for row in recite_store.list_cards("m:devicetwo")] == ["そら"]
    cid = recite_store.list_cards("u:7")[0]["card_id"]
    assert recite_store.delete_card("m:devicetwo", cid) is False
    assert recite_store.count_cards("u:7") == 1


def test_due_cards_include_today_and_skip_retired(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    fresh = recite_store.upsert_card("u:1", _card())
    later = recite_store.upsert_card("u:1", _card(text="そら", zh="天空"))
    done = recite_store.upsert_card("u:1", _card(text="ほし", zh="星星"))
    # Cleared today, so it sits in box 1 — due tomorrow, not now.
    recite_store.bump_card("u:1", later["card_id"], True, NOW)
    for _ in range(srs.MAX_STAGE):
        recite_store.bump_card("u:1", done["card_id"], True, NOW)
    due = [row["card_id"] for row in recite_store.due_cards("u:1", 10, NOW)]
    assert due == [fresh["card_id"]]
    assert recite_store.get_card("u:1", done["card_id"])["retired_at"] > 0
    # Retired cards stay visible in the deck list even though they never queue.
    assert recite_store.count_cards("u:1") == 3


def test_check_ins_accumulate_within_a_day(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    recite_store.mark_day("u:1", "word", 10, NOW - DAY)
    recite_store.mark_day("u:1", "word", 6, NOW)
    recite_store.mark_day("u:1", "word", 4, NOW)
    info = recite_store.deck_streak("u:1", "word", NOW)
    assert info["today"] == 10
    assert info["streak"] == 2
    assert info["day"] == srs.day_key(NOW)
    # Decks check in separately — one does not pay for the other's streak.
    assert recite_store.deck_streak("u:1", "mistake", NOW)["streak"] == 0


# -------------------------------------------------------------------- worker


def test_word_card_kind_follows_the_box(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    rows = [
        recite_store.upsert_card("u:1", _card()),
        recite_store.upsert_card("u:1", _card(text="そら", zh="天空")),
        recite_store.upsert_card("u:1", _card(text="ほし", zh="星星")),
        recite_store.upsert_card("u:1", _card(text="よる", zh="夜晚")),
    ]
    kinds = {}
    for stage in (0, 2, 3, 4):
        row = dict(rows[0], stage=stage)
        session = recite_worker.build_recite_session("word", [row], pool=rows)
        card = session["cards"][0]
        kinds[stage] = card["kind"]
    assert kinds == {0: "meaning", 2: "reverse", 3: "listen", 4: "blank"}


def test_cards_degrade_when_the_word_is_thin(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    # No gloss, no timing, no source line: only a bare word. Rather than ship a
    # broken cloze at box 4, the deck falls back to what it has.
    bare = recite_store.upsert_card(
        "u:1", _card(text="ゆめ", zh="", line_text="", start_ms=0, end_ms=0)
    )
    session = recite_worker.build_recite_session(
        "word", [dict(bare, stage=4)], pool=[bare]
    )
    card = session["cards"][0]
    assert card["kind"] == "meaning"
    assert card["answer"] in [choice["id"] for choice in card["choices"]]


def test_choices_hold_the_answer_once_and_listen_hides_the_word(
    tmp_path, monkeypatch
):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import recite as recite_store

    rows = [
        recite_store.upsert_card("u:1", _card()),
        recite_store.upsert_card("u:1", _card(text="そら", zh="天空")),
        recite_store.upsert_card("u:1", _card(text="ほし", zh="星星")),
        recite_store.upsert_card("u:1", _card(text="よる", zh="夜晚")),
    ]
    session = recite_worker.build_recite_session(
        "word", [dict(rows[0], stage=3)], pool=rows
    )
    card = session["cards"][0]
    assert card["kind"] == "listen"
    assert card["audio"] is True
    texts = [choice["text"] for choice in card["choices"]]
    assert len(texts) == len(set(texts))
    assert texts.count("なみだ") == 1
    answer = next(c for c in card["choices"] if c["id"] == card["answer"])
    assert answer["text"] == "なみだ"
    # A listening card that prints the word it is asking for teaches nothing.
    assert "なみだ" not in card["stem"]
    assert "なみだ" not in card["prompt"]
    # The anchor still travels with the card so the miss screen can play it.
    assert card["detail"]["start_ms"] == 1000
    assert card["detail"]["song_id"] == "s1"

    blank = recite_worker.build_recite_session(
        "word", [dict(rows[0], stage=4)], pool=rows
    )["cards"][0]
    assert blank["kind"] == "blank"
    assert blank["stem"] == "____ が こぼれる"
    assert blank["blank"] == {"before": "", "gap": "なみだ", "after": " が こぼれる"}


def test_deck_summary_splits_new_learning_and_mastered():
    states = [
        {"due_at": NOW - DAY, "reps": 0, "retired": False},
        {"due_at": NOW + 9 * DAY, "reps": 3, "retired": False},
        {"due_at": NOW, "reps": 1, "retired": False},
        {"due_at": 0, "reps": 6, "retired": True},
    ]
    summary = recite_worker.deck_summary(
        "word", states, {"streak": 4, "today": 12, "day": srs.day_key(NOW)}, NOW
    )
    assert summary["total"] == 4
    assert summary["due"] == 2  # the new one and the one due today
    assert summary["new"] == 1
    assert summary["learning"] == 2
    assert summary["mastered"] == 1
    assert summary["streak"] == 4
    assert summary["today"] == 12
    assert summary["sizes"] == list(recite_worker.SESSION_SIZES)


def test_mistake_ref_survives_a_round_trip():
    row = {"song_id": "s1", "qkind": "word", "item_key": "s1:走る|1000"}
    ref = recite_worker.mistake_ref(row)
    assert recite_worker.parse_mistake_ref(ref) == ("s1", "word", "s1:走る|1000")
    assert recite_worker.parse_mistake_ref("") == ("", "", "")


def test_clamp_size_stays_on_the_offered_sizes():
    assert recite_worker.clamp_size(0) == 10
    assert recite_worker.clamp_size(20) == 20
    assert recite_worker.clamp_size(999) == 30
    assert recite_worker.clamp_size("nope") == recite_worker.DEFAULT_SIZE


# ----------------------------------------------------------------------- api


def test_word_deck_api_round_trip(tmp_path, monkeypatch):
    main, _store = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        empty = client.get("/api/learn/deck", headers=head).json()
        assert empty["deck"] == "word"
        assert empty["total"] == 0
        assert empty["cards"] == []
        assert empty["streak"] == 0
        # Nothing collected yet, so a session has nothing to hand back.
        assert client.get("/api/learn/session", headers=head).status_code == 409

        added = client.post("/api/learn/cards", json=_card(), headers=head)
        assert added.status_code == 200
        cid = added.json()["card"]["card_id"]
        assert added.json()["total"] == 1
        imported = client.post(
            "/api/learn/cards/import",
            json={"cards": [_card(), _card(text="そら", zh="天空")]},
            headers=head,
        )
        assert imported.status_code == 200
        assert imported.json()["added"] == 1  # the first one was already there
        assert imported.json()["deck"]["total"] == 2

        deck = client.get("/api/learn/deck", headers=head).json()
        assert deck["total"] == 2
        assert deck["due"] == 2
        assert deck["new"] == 2
        assert deck["mastered"] == 0
        first = next(row for row in deck["cards"] if row["card_id"] == cid)
        assert first["line_text"] == "なみだ が こぼれる"
        assert first["start_ms"] == 1000
        assert first["retired"] is False
        # `cards=0` is the campaign header's cheap read: counts, no rows.
        assert client.get("/api/learn/deck?cards=0", headers=head).json()["cards"] == []

        session = client.get("/api/learn/session?size=20", headers=head).json()
        assert session["schema"] == recite_worker.RECITE_SCHEMA
        assert session["size"] == 20
        assert len(session["cards"]) == 2
        assert all(card["choices"] for card in session["cards"])

        graded = client.post(
            "/api/learn/session",
            json={
                "deck": "word",
                "answers": [
                    {"card_id": cid, "ok": True},
                    {"card_id": cid, "ok": False},  # duplicate, must be ignored
                ],
            },
            headers=head,
        )
        assert graded.status_code == 200
        body = graded.json()
        assert body["graded"] == 1
        assert body["correct"] == 1
        assert body["pct"] == 100
        assert body["deck"]["streak"] == 1
        assert body["deck"]["today"] == 1
        after = next(
            row for row in body["deck"]["cards"] if row["card_id"] == cid
        )
        assert after["stage"] == 1
        assert after["reps"] == 1
        assert after["due_at"] > 0
        # The answered card is a day out now; only the untouched one is left.
        assert body["deck"]["due"] == 1

        dropped = client.delete(f"/api/learn/cards/{cid}", headers=head)
        assert dropped.status_code == 200
        assert dropped.json()["total"] == 1
        assert client.delete(f"/api/learn/cards/{cid}", headers=head).status_code == 404


def test_deck_api_rejects_junk(tmp_path, monkeypatch):
    main, _store = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        assert client.post("/api/learn/cards", json={}, headers=head).status_code == 400
        assert (
            client.post(
                "/api/learn/cards/import", json={"cards": "nope"}, headers=head
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/learn/session", json={"answers": "nope"}, headers=head
            ).status_code
            == 400
        )
        # An unknown deck name falls back to the word deck rather than 4xx-ing.
        assert (
            client.get("/api/learn/deck?deck=hades", headers=head).json()["deck"]
            == "word"
        )


def test_two_devices_keep_separate_decks(tmp_path, monkeypatch):
    main, _store = _boot(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        one = {"x-lovktv-machine": "deviceone"}
        two = {"x-lovktv-machine": "devicetwo"}
        client.post("/api/learn/cards", json=_card(), headers=one)
        assert client.get("/api/learn/deck", headers=one).json()["total"] == 1
        assert client.get("/api/learn/deck", headers=two).json()["total"] == 0
        assert client.get("/api/learn/session", headers=two).status_code == 409


def test_mistake_deck_rides_the_learn_mistakes_row(tmp_path, monkeypatch):
    main, _store = _boot(tmp_path, monkeypatch)
    from lovktv.storage import learn as learn_store

    owner = "m:deviceone"
    learn_store.record_mistake(
        owner,
        "s1",
        qkind="word",
        item_key="s1:走る",
        prompt="「走る」是什么意思？",
        stem="走る",
        answer_text="奔跑",
        payload={
            "id": "q1",
            "kind": "word",
            "prompt": "「走る」是什么意思？",
            "stem": "走る",
            "choices": [
                {"id": "a", "text": "奔跑"},
                {"id": "b", "text": "记忆"},
                {"id": "c", "text": "天空"},
                {"id": "d", "text": "夜晚"},
            ],
            "answer": "a",
            "knowledge": {"key": "s1:走る", "text": "走る", "zh": "奔跑"},
        },
    )
    with TestClient(main.app) as client:
        head = {"x-lovktv-machine": "deviceone"}
        deck = client.get("/api/learn/deck?deck=mistake", headers=head).json()
        assert deck["deck"] == "mistake"
        assert deck["total"] == 1
        assert deck["due"] == 1
        assert deck["cards"][0]["wrong_count"] == 1
        ref = deck["cards"][0]["card_id"]
        assert ref == "s1|word|s1:走る"
        # The word deck is untouched: a mistake never forks a `learn_cards` row.
        assert client.get("/api/learn/deck", headers=head).json()["total"] == 0

        session = client.get("/api/learn/session?deck=mistake", headers=head).json()
        assert session["deck"] == "mistake"
        card = session["cards"][0]
        assert card["card_id"] == ref
        assert card["detail"]["text"] == "走る"
        assert [choice["text"] for choice in card["choices"]].count("奔跑") == 1

        graded = client.post(
            "/api/learn/session",
            json={"deck": "mistake", "answers": [{"card_id": ref, "ok": True}]},
            headers=head,
        )
        assert graded.status_code == 200
        assert graded.json()["graded"] == 1
        assert graded.json()["deck"]["streak"] == 1
        row = learn_store.list_open_mistakes(owner)[0]
        assert row["stage"] == 1
        assert row["reps"] == 1
        assert row["due_at"] > 0
        # Nothing due today any more, so the deck has no round to hand out.
        assert (
            client.get("/api/learn/session?deck=mistake", headers=head).status_code
            == 409
        )


def test_a_missed_mistake_drops_back_and_repeats(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    from lovktv.storage import learn as learn_store

    owner = "m:deviceone"
    learn_store.record_mistake(
        owner, "s1", qkind="word", item_key="s1:走る", stem="走る", answer_text="奔跑"
    )
    for _ in range(3):
        learn_store.bump_mistake(owner, "s1", "word", "s1:走る", True, NOW)
    climbed = learn_store.list_open_mistakes(owner)[0]
    assert climbed["stage"] == 3
    learn_store.bump_mistake(owner, "s1", "word", "s1:走る", False, NOW)
    slipped = learn_store.list_open_mistakes(owner)[0]
    assert slipped["stage"] == 1
    assert slipped["due_at"] <= srs.end_of_day(NOW)
    assert [row["item_key"] for row in learn_store.list_due_mistakes(owner, 10, NOW)] == [
        "s1:走る"
    ]
    # Clearing the top box resolves the row — out of the notebook for good.
    for _ in range(srs.MAX_STAGE):
        learn_store.bump_mistake(owner, "s1", "word", "s1:走る", True, NOW)
    assert learn_store.list_open_mistakes(owner) == []
    assert learn_store.count_open_mistakes(owner) == 0
