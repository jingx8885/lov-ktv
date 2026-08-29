"""UI locale for API errors. Keys match frontend `api.*` entries."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from starlette.requests import Request
from starlette.websockets import WebSocket

from lovktv.config import ROOT

LOCALES = ("zh", "yue", "en", "ja")
_LOCALE_DIR = ROOT / "frontend" / "public" / "shared" / "i18n" / "locales"
_PAIR = re.compile(r'"((?:api)\.[^"]+)":\s*"((?:\\.|[^"\\])*)"')
_ERROR_PREFIXES = (
    ("分离降级：", "api.sep_degrade"),
    ("注音降级：", "api.ann_degrade"),
    ("翻译降级：", "api.tr_degrade"),
    ("MTV降级：", "api.mtv_degrade"),
)
_EXC_KEYS = {
    "还没配置微信开放平台 AppID": "api.wechat_not_configured",
    "微信取消了授权": "api.wechat_denied",
    "微信授权失败": "api.wechat_auth_failed",
    "读取微信资料失败": "api.wechat_profile_failed",
    "二维码无效": "api.qr_invalid",
    "二维码已过期，请刷新": "api.qr_expired",
    "请先登录": "api.need_login",
    "缺少 q": "api.missing_q",
    "无效的试听 id": "api.bad_preview_id",
    "这首暂时不能试听": "api.preview_unavailable",
    "缺少 query": "api.missing_query",
    "缺少 lines": "api.missing_lines",
    "歌曲不存在": "api.song_not_found",
    "只有失败的歌可以重试": "api.retry_only_failed",
    "这首还没有歌词": "api.no_lyrics",
    "没有歌词": "api.no_lyrics",
    "歌词还不能用来学习": "api.lyrics_not_ready",
    "歌词还不能用来玩": "api.lyrics_not_ready",
    "这首没有可学的句子": "api.no_learn_lines",
    "这首没有可玩的句子": "api.no_learn_lines",
    "这首还没就绪，不能点": "api.not_ready",
    "局域网地址无效": "api.bad_lan",
    "未知命令": "api.unknown_command",
    "无效的设备": "api.bad_device",
    "微信未返回账号": "api.wechat_no_account",
}


def parse_lang(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    first = text.split(",", 1)[0].split(";", 1)[0].strip()
    if first in LOCALES:
        return first
    if (
        first.startswith("yue")
        or first.startswith("zh-hk")
        or first.startswith("zh-mo")
    ):
        return "yue"
    if first.startswith("ja"):
        return "ja"
    if first.startswith("en"):
        return "en"
    if first.startswith("zh"):
        return "zh"
    blob = text.replace(" ", "")
    if "yue" in blob or "zh-hk" in blob or "zh-mo" in blob:
        return "yue"
    if blob.startswith("ja") or ",ja" in blob:
        return "ja"
    if blob.startswith("en") or ",en" in blob:
        return "en"
    if blob.startswith("zh") or "zh-" in blob:
        return "zh"
    return ""


def request_lang(request: Request | None) -> str:
    if request is None:
        return "zh"
    query = parse_lang(request.query_params.get("lang"))
    if query:
        return query
    return parse_lang(request.headers.get("accept-language")) or "zh"


def ws_lang(ws: WebSocket) -> str:
    return (
        parse_lang(ws.query_params.get("lang") or ws.headers.get("accept-language"))
        or "zh"
    )


@lru_cache(maxsize=8)
def load_pack(lang: str) -> dict[str, str]:
    code = lang if lang in LOCALES else "zh"
    path = _LOCALE_DIR / f"{code}.js"
    text = path.read_text(encoding="utf-8")
    pack = {}
    for key, value in _PAIR.findall(text):
        pack[key] = value.replace("\\n", "\n").replace('\\"', '"')
    return pack


def locale_keys(lang: str = "zh") -> set[str]:
    return set(load_pack(lang))


def translate(lang: str, key: str, **vars: Any) -> str:
    pack = load_pack(lang if lang in LOCALES else "zh")
    text = pack.get(key) or load_pack("zh").get(key) or key
    for name, value in vars.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def t(request: Request | None, key: str, **vars: Any) -> str:
    return translate(request_lang(request), key, **vars)


def localize_error_text(lang: str, message: str) -> str:
    raw = str(message or "")
    if not raw:
        return raw
    key = _EXC_KEYS.get(raw)
    if key:
        return translate(lang, key)
    for prefix, prefix_key in _ERROR_PREFIXES:
        if raw.startswith(prefix):
            return translate(lang, prefix_key) + raw[len(prefix) :]
    if raw.startswith("搜索失败："):
        return translate(lang, "api.search_failed", exc=raw.split("：", 1)[1])
    if raw.startswith("日语注音失败："):
        return translate(lang, "api.ja_annotate_failed", exc=raw.split("：", 1)[1])
    return raw


def localize_exc(request: Request | None, exc: BaseException) -> str:
    return localize_error_text(request_lang(request), str(exc))


def localize_song(lang: str, song: dict | None) -> dict | None:
    if not song:
        return song
    error = song.get("error")
    if not error:
        return song
    out = dict(song)
    out["error"] = localize_error_text(lang, str(error))
    return out
