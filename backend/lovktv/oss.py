from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
from email.utils import formatdate
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

from lovktv.config import (
    ALIYUN_OSS_ACCESS_KEY_ID,
    ALIYUN_OSS_ACCESS_KEY_SECRET,
    ALIYUN_OSS_BASE_PATH,
    ALIYUN_OSS_BUCKET_NAME,
    ALIYUN_OSS_DOWNLOAD_DOMAIN,
    ALIYUN_OSS_ENABLED,
    ALIYUN_OSS_ENDPOINT,
    MEDIA_DIR,
)

PUBLISH_NAMES = (
    "karaoke.m4a",
    "original.mp3",
    "guide.m4a",
    "mtv.mp4",
    "cover.jpg",
    "lyrics.json",
    "lyrics.lrc",
    "lyrics.elrc",
    "lyrics.ass",
    "lyrics.manual.lrc",
    "ja-annotate.json",
    "zh-translate.json",
    "skeleton.json",
    "mugen.ass",
    "oss.json",
)

_REMOTE_CACHE: dict[str, bool] = {}

MEDIA_CORS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CORSConfiguration>
  <CORSRule>
    <AllowedOrigin>*</AllowedOrigin>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>HEAD</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
    <ExposeHeader>ETag</ExposeHeader>
    <ExposeHeader>x-oss-request-id</ExposeHeader>
    <MaxAgeSeconds>3600</MaxAgeSeconds>
  </CORSRule>
</CORSConfiguration>
"""


def oss_ready() -> bool:
    return bool(
        ALIYUN_OSS_ENABLED
        and ALIYUN_OSS_ACCESS_KEY_ID
        and ALIYUN_OSS_ACCESS_KEY_SECRET
        and ALIYUN_OSS_BUCKET_NAME
        and ALIYUN_OSS_ENDPOINT
    )


def oss_status() -> dict[str, Any]:
    return {
        "enabled": oss_ready(),
        "bucket": bool(ALIYUN_OSS_BUCKET_NAME),
        "endpoint": bool(ALIYUN_OSS_ENDPOINT),
        "download": bool(ALIYUN_OSS_DOWNLOAD_DOMAIN),
    }


def object_key(song_id: str, name: str) -> str:
    prefix = (ALIYUN_OSS_BASE_PATH or "lovktv").strip("/")
    return f"{prefix}/{song_id}/{name}"


def public_url(song_id: str, name: str) -> str:
    base = (ALIYUN_OSS_DOWNLOAD_DOMAIN or "").rstrip("/")
    if not base:
        host = ALIYUN_OSS_ENDPOINT.removeprefix("https://").removeprefix("http://")
        base = f"https://{ALIYUN_OSS_BUCKET_NAME}.{host}"
    return f"{base}/{object_key(song_id, name)}"


def _content_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def _endpoint_host() -> str:
    host = (
        ALIYUN_OSS_ENDPOINT.removeprefix("https://").removeprefix("http://").strip("/")
    )
    return host


def _sign(
    method: str,
    key: str,
    content_type: str = "",
    extra: dict[str, str] | None = None,
    content_md5: str = "",
    subresource: str = "",
) -> dict[str, str]:
    date = formatdate(usegmt=True)
    headers = {"Date": date}
    if content_md5:
        headers["Content-MD5"] = content_md5
    canonical = ""
    if extra:
        for name in sorted(extra):
            headers[name] = extra[name]
            canonical += f"{name.lower()}:{extra[name]}\n"
    if content_type:
        headers["Content-Type"] = content_type
    resource = (
        f"/{ALIYUN_OSS_BUCKET_NAME}/{key}" if key else f"/{ALIYUN_OSS_BUCKET_NAME}/"
    )
    if subresource:
        resource = (
            f"/{ALIYUN_OSS_BUCKET_NAME}/{key}?{subresource}"
            if key
            else f"/{ALIYUN_OSS_BUCKET_NAME}/?{subresource}"
        )
    string = f"{method}\n{content_md5}\n{content_type}\n{date}\n{canonical}{resource}"
    digest = hmac.new(
        ALIYUN_OSS_ACCESS_KEY_SECRET.encode("utf-8"),
        string.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")
    headers["Authorization"] = f"OSS {ALIYUN_OSS_ACCESS_KEY_ID}:{signature}"
    return headers


def _object_url(key: str, subresource: str = "") -> str:
    path = quote(key) if key else ""
    url = f"https://{ALIYUN_OSS_BUCKET_NAME}.{_endpoint_host()}/{path}"
    if subresource:
        return f"{url}?{subresource}"
    return url


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def cors_allows_media(xml: str) -> bool:
    if not xml:
        return False
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False
    for rule in list(root):
        if _local_name(rule.tag) != "CORSRule":
            continue
        origins = set()
        methods = set()
        for el in list(rule):
            name = _local_name(el.tag)
            value = (el.text or "").strip()
            if name == "AllowedOrigin":
                origins.add(value)
            elif name == "AllowedMethod":
                methods.add(value.upper())
        if (
            origins.intersection({"*", "https://ktv.lovbrowser.com"})
            and "GET" in methods
        ):
            return True
    return False


def merge_cors_xml(existing: str | None) -> str:
    if existing and cors_allows_media(existing):
        return existing
    if not existing:
        return MEDIA_CORS_XML
    try:
        root = ET.fromstring(existing)
    except ET.ParseError:
        return MEDIA_CORS_XML
    extra = ET.fromstring(MEDIA_CORS_XML)
    for rule in list(extra):
        if _local_name(rule.tag) == "CORSRule":
            root.append(rule)
    return ET.tostring(root, encoding="unicode")


def ensure_bucket_cors() -> str:
    if not oss_ready():
        return "disabled"
    get_headers = _sign("GET", "", subresource="cors")
    with httpx.Client(timeout=20.0) as client:
        current = client.get(_object_url("", "cors"), headers=get_headers)
        existing = current.text if current.status_code == 200 else None
        if current.status_code not in {200, 404}:
            current.raise_for_status()
        body = merge_cors_xml(existing)
        if existing and body == existing:
            return "already"
        raw = body.encode("utf-8")
        digest = base64.b64encode(hashlib.md5(raw).digest()).decode("ascii")
        put_headers = _sign(
            "PUT", "", "application/xml", content_md5=digest, subresource="cors"
        )
        put_headers["Content-Length"] = str(len(raw))
        res = client.put(_object_url("", "cors"), headers=put_headers, content=raw)
        res.raise_for_status()
    return "applied"


def put_file(song_id: str, path: Path) -> str:
    if not oss_ready():
        raise RuntimeError("oss disabled")
    key = object_key(song_id, path.name)
    ctype = _content_type(path.name)
    extra = {"x-oss-object-acl": "public-read"}
    headers = _sign("PUT", key, ctype, extra)
    data = path.read_bytes()
    headers["Content-Length"] = str(len(data))
    with httpx.Client(timeout=300.0) as client:
        res = client.put(_object_url(key), headers=headers, content=data)
        res.raise_for_status()
    return public_url(song_id, path.name)


def head_object(song_id: str, name: str) -> bool:
    if not oss_ready():
        return False
    cache_key = f"{song_id}/{name}"
    if cache_key in _REMOTE_CACHE:
        return _REMOTE_CACHE[cache_key]
    key = object_key(song_id, name)
    headers = _sign("HEAD", key)
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.head(_object_url(key), headers=headers)
        ok = res.status_code == 200
    except httpx.HTTPError:
        ok = False
    _REMOTE_CACHE[cache_key] = ok
    return ok


def write_marker(song_id: str, names: list[str]) -> Path:
    folder = MEDIA_DIR / song_id
    folder.mkdir(parents=True, exist_ok=True)
    native = False
    lyrics = folder / "lyrics.json"
    if lyrics.exists():
        try:
            data = json.loads(lyrics.read_text(encoding="utf-8"))
            native = data.get("native_video") is True
        except (OSError, json.JSONDecodeError):
            native = False
    if not native:
        native = (MEDIA_DIR / song_id / "mugen.mp4").exists() or (
            MEDIA_DIR / song_id / "mugen.webm"
        ).exists()
    from lovktv.store import media_rev

    payload = {"files": names, "native_video": native, "media_rev": media_rev(song_id)}
    dest = folder / "oss.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return dest


def publish_files(folder: Path) -> list[Path]:
    names = set(PUBLISH_NAMES)
    files: list[Path] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name == "oss.json":
            continue
        if path.name in names or path.suffix.lower() == ".json":
            files.append(path)
    return files


def publish_song(song_id: str) -> list[str]:
    if not oss_ready():
        return []
    folder = MEDIA_DIR / song_id
    if not folder.exists():
        return []
    uploaded: list[str] = []
    for path in publish_files(folder):
        put_file(song_id, path)
        uploaded.append(path.name)
        _REMOTE_CACHE[f"{song_id}/{path.name}"] = True
    marker = write_marker(song_id, uploaded)
    put_file(song_id, marker)
    uploaded.append("oss.json")
    return uploaded


def publish_all(song_ids: list[str] | None = None) -> dict[str, list[str]]:
    ids = song_ids or [p.name for p in MEDIA_DIR.iterdir() if p.is_dir()]
    result: dict[str, list[str]] = {}
    for song_id in ids:
        result[song_id] = publish_song(song_id)
    return result


def remote_native(song_id: str) -> bool:
    folder = MEDIA_DIR / song_id
    marker = folder / "oss.json"
    if marker.exists():
        try:
            return bool(
                json.loads(marker.read_text(encoding="utf-8")).get("native_video")
            )
        except (OSError, json.JSONDecodeError):
            return False
    return head_object(song_id, "mtv.mp4") or head_object(song_id, "lyrics.json")
