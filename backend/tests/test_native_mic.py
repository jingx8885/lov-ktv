from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_phone_desk_mic_uses_native_udp_not_webrtc():
    rtc = (ROOT / "phone" / "room" / "js" / "rtc.js").read_text(encoding="utf-8")
    native = (ROOT / "phone" / "room" / "js" / "native-mic.js").read_text(encoding="utf-8")
    mix = (ROOT / "phone" / "room" / "js" / "mix.js").read_text(encoding="utf-8")
    player = (ROOT / "phone" / "player" / "js" / "mic.js").read_text(encoding="utf-8")
    assert "hasNativeMic" in native
    assert "nativeCapabilities" in rtc
    assert 'nativeCall("startTvMic")' in rtc
    assert "getUserMedia" not in rtc
    assert "nativeCall" in native
    assert "nativeMicState().tv" in mix
    assert 'nativeCall("startIem")' in player
    assert "startNativePhoneMic" in player
    assert "nativeCall" in player


def test_native_mic_copy_mentions_lan_not_webrtc():
    zh = (ROOT / "shared" / "i18n" / "locales" / "zh.js").read_text(encoding="utf-8")
    assert '"phone.mic.needTv"' in zh
    assert "WebRTC" in zh
    assert '"phone.mic.hintNativeIem"' in zh
    assert zh.count('"phone.mic.needTv"') == 1
