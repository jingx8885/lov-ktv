from lovktv.pipeline.language import detect_language, resolve_language, whisper_language


def test_detect_english():
    assert detect_language("What's waited till tomorrow starts tonight") == "en"


def test_detect_mandarin():
    assert detect_language("我听见雨落在窗台") == "zh"


def test_detect_cantonese_from_particles():
    assert detect_language("今晚夜空好美麗 你喺我心裡面 冇人比你更好") == "yue"


def test_detect_cantonese_from_hint():
    assert detect_language("今晚夜空好美丽", "粤语") == "yue"
    assert detect_language("今晚夜空好美丽", "yue") == "yue"


def test_detect_japanese_wins_over_han():
    assert detect_language("目まぐるしい時間の群れが") == "ja"


def test_romaji_stays_english_without_hint():
    assert detect_language("moshimo negai hitotsu dake") == "en"


def test_romaji_follows_ja_hint():
    assert detect_language("moshimo negai hitotsu dake", "ja") == "ja"
    assert resolve_language("moshimo negai hitotsu dake", "en", "ja") == "ja"
    assert resolve_language("It's only love", "zh") == "en"


def test_whisper_language_keeps_yue():
    assert whisper_language("yue") == "yue"
    assert whisper_language("cantonese") == "zh"
    assert whisper_language("en") == "en"
