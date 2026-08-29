from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from lovktv.assets import VersionedStaticFiles
from lovktv.config import MEDIA_DIR, PUBLIC_URL, ROOT, SESSION_DAYS
from lovktv.host_volume import host_volume_meta, set_host_volume
from lovktv.jobs import job_queue
from lovktv.runtime import _mics, _peers, _rooms
from lovktv import store
from lovktv.store import init_db
from lovktv.services.http import clear_session, current_user, fail, request_base, set_host_cookie, set_session
from lovktv.services.room_runtime import bind_host, host_machine, request_ip, room_view, run_command, broadcast
from lovktv.catalog.fetch import open_preview_stream, search_songs, resolve_audio_source, is_preview_id
from lovktv.catalog.mugen import is_mugen_kid
from lovktv.agents.ja_lyrics import agent_status, annotate_ja_lines
from lovktv.pipeline.mdx_onnx import model_status

_PUBLIC = ROOT / "frontend" / "public"
_DIST = ROOT / "frontend" / "frontend-dist"
WEB = _DIST if (_DIST / "manifest.json").is_file() else _PUBLIC
HOST_COOKIE = "lovktv_host"
HOST_COOKIE_DAYS = 400


class NoStoreHtmlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.endswith(".html") or request.url.path in {"/", "/m.html", "/tv.html", "/login.html"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    from lovktv.catalog.mugen_index import prefetch_index
    from lovktv.oss import ensure_bucket_cors, oss_ready
    from lovktv.store import init_db
    from lovktv.jobs import resume_stuck_jobs
    _.state.ready = False
    job_queue.start()
    try:
        init_db()
        resume_stuck_jobs()
        prefetch_index()
        if oss_ready():
            try:
                print(f"[lovktv] oss cors {ensure_bucket_cors()}", flush=True)
            except Exception as exc:
                print(f"[lovktv] oss cors skipped: {exc}", flush=True)
        _.state.ready = True
        yield
    finally:
        _.state.ready = False
        job_queue.stop()


app = FastAPI(title="lov-ktv", lifespan=lifespan)
app.add_middleware(NoStoreHtmlMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/healthz", include_in_schema=False)
def healthz(request: Request):
    worker = job_queue.health()
    ready = bool(getattr(request.app.state, "ready", False)) and worker["running"]
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "ok" if ready else "starting", "ready": ready, "worker": worker}, status_code=200 if ready else 503)

from lovktv.routers import auth, media, misc, rooms, songs  # noqa: E402

app.include_router(misc.router)
app.include_router(auth.router)
app.include_router(songs.router)
app.include_router(rooms.router)
app.include_router(media.router)

# Compatibility facade: existing integrations import route callables and
# mutable room state from ``lovktv.main``.
for _module in (misc, auth, songs, rooms, media):
    for _name in dir(_module):
        if _name.startswith("api_") or _name in {"ws_room", "media", "mobile_page", "login_page"}:
            globals()[_name] = getattr(_module, _name)

if WEB.exists():
    app.mount("/", VersionedStaticFiles(directory=WEB, html=True), name="web")

__all__ = ["app", "MEDIA_DIR", "PUBLIC_URL", "ROOT", "WEB", "HOST_COOKIE", "HOST_COOKIE_DAYS",
           "_rooms", "_peers", "_mics", "host_volume_meta", "set_host_volume", "request_base",
           "current_user", "set_session", "clear_session", "fail", "room_view", "run_command", "broadcast",
           "bind_host", "host_machine", "request_ip", "healthz", "open_preview_stream", "search_songs",
           "resolve_audio_source", "is_preview_id", "is_mugen_kid", "agent_status", "annotate_ja_lines",
           "model_status"]
