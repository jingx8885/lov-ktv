"""Catalog API exports grouped by search, lyrics, audio and import duties."""

from .audio import (
    _AUDIO_CACHE,
    _list_ytdlp,
    _open_ytdlp_stream,
    _pick_best_match,
    _resolve_bilibili_source,
    _resolve_netease_source,
    _resolve_ytdlp_source,
    _ytdlp_direct_url,
    _ytdlp_download,
    forget_audio_source,
    is_preview_id,
    open_bilibili_audio,
    open_netease_audio,
    open_preview_stream,
    peek_audio_source,
    pick_bilibili_mv,
    probe_netease_url,
    remember_audio_source,
    resolve_audio_source,
    try_bilibili_download,
    try_netease_download,
    try_ytdlp_search,
)
from .http import curl_proxy_args, urlopen, ytdlp_proxy_args
from .importer import _complete_mugen_audio, import_song
from .kugou import fetch_kugou_lyrics
from .lyrics import LRC_LINE, META_PREFIX, fetch_lyric, parse_lrc
from .mugen import (
    import_mugen_song,
    is_mugen_kid,
    open_mugen_preview,
    pick_vocal_hit,
    search_mugen,
)
from .netease import eapi_play_url, media_request
from .search import (
    BAD_TITLE_TOKENS,
    BROWSER_UA,
    SEARCH_CHANNELS,
    TITLE_VERSION,
    TONZHON_API,
    clean_search_title,
    flatten_artists,
    is_clean_title,
    merge_channel_hits,
    post_form,
    search_bilibili_hits,
    search_songs,
    search_tonzhon,
    search_ytdlp_hits,
)

__all__ = [name for name in globals() if not name.startswith("__")]
