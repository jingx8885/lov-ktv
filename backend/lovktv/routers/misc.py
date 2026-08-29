from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from starlette.requests import Request
from lovktv.agents.ja_lyrics import agent_status
from lovktv.apps import catalog as apps_catalog, download_apk, require_upload_token, save_apk
from lovktv.assets import asset_rev
from lovktv.config import ROOT
from lovktv.db import dialect as db_dialect
from lovktv.oss import oss_status
from lovktv.pipeline.mdx_onnx import model_status
from lovktv.runtime import web_root

router = APIRouter()


@router.get("/api/host")
def api_host(request: Request) -> dict:
    from lovktv.services.http import request_base
    from lovktv import store
    return {
        "origin": request_base(request),
        "process_origin": request_base(request),
        "mode": "server",
        "phone_path": "/m.html?room=",
        "cache_ready": 0,
        "mic_port": 0,
        "mic_sample_rate": 48000,
        "models": model_status(),
        "oss": oss_status(),
        "agent": agent_status(),
        "database": db_dialect(store.DB_PATH),
        "asset_rev": asset_rev(web_root()),
    }


@router.get("/api/apps")
def api_apps() -> dict:
    return apps_catalog()


@router.get("/api/apps/{channel}")
@router.get("/apps/{channel}.apk")
def api_app_download(channel: str):
    return download_apk(channel)


@router.post("/api/apps/{channel}")
async def api_app_upload(channel: str, request: Request, file: UploadFile = File(...), version: str = Form("")) -> dict:
    require_upload_token(request)
    return save_apk(channel, file.file, version)
