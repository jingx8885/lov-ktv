# lov-ktv

[简体中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [粵語](README.yue.md)

A self-hosted karaoke system for homes and private rooms. Guests search and queue songs from their phones, the server downloads and processes audio, and a TV or browser plays the result with synchronized lyrics.

[Live demo](https://ktv.lovbrowser.com) · [TV player](https://ktv.lovbrowser.com/tv.html) · [Mobile remote](https://ktv.lovbrowser.com/m.html)

## Features

- **Search-first library**: search by song title instead of preparing files in advance; local upload is a fallback.
- **Automatic processing**: retrieves timestamped official LRC when available, separates vocals with ONNX Runtime, and uses the no-Torch faster-whisper runtime for word-level vocal alignment; it still falls back to LRC/onset when Whisper is unavailable.
- **Multi-device rooms**: the TV displays a room QR code; phones can search, queue, prioritize, skip, and control playback.
- **Multiple hosts**: use the browser TV player, Android TV host, or native Android phone remote.
- **Offline cache**: Android TV keeps completed songs playable when the processing server is temporarily unavailable.
- **Flexible storage**: SQLite and local media are the defaults, with optional PostgreSQL and Alibaba Cloud OSS support.

## How it works

```text
Phone / remote  ── search, queue, control ──▶  lov-ktv server
       │                                         │
       │                                         ├─ audio and LRC retrieval
       │                                         ├─ ONNX vocal separation
       │                                         └─ result and lyric storage
       │                                                       │
       └──────────── join room by QR code ─────────▶  TV / browser player
```

The audio pipeline tries NetEase previews, SoundCloud, and YouTube in sequence. Official LRC is preferred, so karaoke remains usable without a speech-to-text service.

## Quick start

### Docker Compose (recommended)

Docker and Docker Compose are required.

```bash
git clone https://github.com/jingx8885/lov-ktv.git
cd lov-ktv
cp .env.example .env
docker compose up -d --build
```

Once ready, open:

- TV player: <http://localhost:8787/tv.html>
- Mobile remote: <http://localhost:8787/m.html>
- Service status: <http://localhost:8787/api/host>

For TVs and phones on your LAN, replace `localhost` with the address of the computer or NAS running lov-ktv. The `models.separator` and `models.whisper` values returned by `/api/host` should be `true` for production-quality vocal alignment.

### Local Python setup

Python 3.11+ is required. The complete source fallback chain also needs FFmpeg and yt-dlp.

```bash
python -m venv .venv
# Linux / macOS
.venv/bin/pip install -e backend
PYTHONPATH=backend .venv/bin/uvicorn lovktv.main:app --host 0.0.0.0 --port 8787
```

On Windows PowerShell, run `.venv\Scripts\python -m pip install -e backend`, set `PYTHONPATH=backend`, and start Uvicorn.

## Android apps

- [Android TV](android-tv/README.md): LAN host, completed-song cache, and receiver for low-latency UDP microphone audio from a phone.
- [Android phone](android-phone/README.md): native song remote, playback controls, and low-latency microphone streaming to the TV.

The mobile web UI can also queue songs, but low-latency microphone audio requires both native Android apps.

## Configuration

Copy `.env.example` to `.env` and fill in only what you need. Every integration is optional: without a database URL the app uses `data/lovktv.sqlite`; without object storage it uses `data/media`.

| Variable | Purpose |
| --- | --- |
| `LOVKTV_PUBLIC_URL` | Public base URL and OAuth callback origin |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | WeChat Open Platform sign-in |
| `WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET` | Sign-in inside WeChat Official Accounts |
| `LOVKTV_DATABASE_URL` | PostgreSQL connection string |
| `ALIYUN_OSS_*` | Alibaba Cloud OSS storage for processed media |
| `LOVKTV_HTTPS_PROXY` | HTTPS proxy used only by NetEase preview / yt-dlp downloads |

Do not commit `.env`, secrets, `data/`, a media library, or built APK files.

## Documentation

- [Product specification](docs/SPEC.md)
- [Epic / issue graph](docs/GRAPH.md)
- [API reference](docs/api.md)
- [Data model](docs/schema.md)

## Copyright and license

Original code in this project is licensed under the [Apache License 2.0](LICENSE).

Third-party dependencies, reference projects, and content under `vendor/` remain subject to their respective licenses; lovjpn is licensed under PolyForm Noncommercial. Songs, lyrics, cover art, and videos belong to their respective rights holders. You are responsible for complying with local law and content-platform terms when deploying lov-ktv. Do not publicly distribute media without authorization.
