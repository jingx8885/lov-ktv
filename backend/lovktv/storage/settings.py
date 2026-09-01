"""Runtime settings: admin/database values override environment defaults."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from lovktv.core.db import connect as db_connect
from lovktv.core.db import execute

_LOCK = threading.Lock()
_TRUE = {"1", "true", "yes", "on"}


def _connect():
    # Tests and embedded deployments may rebind store.DB_PATH at runtime.
    from lovktv.storage import store

    return db_connect(store.DB_PATH)

# Secrets remain environment-only. These are operational switches and knobs
# that are safe to edit from the authenticated admin console.
SETTINGS: dict[str, dict[str, Any]] = {
    "points_enabled": {"env": "LOVKTV_POINTS", "default": False, "type": "bool", "label": "启用积分"},
    "queue_cost": {"env": "LOVKTV_QUEUE_COST", "default": 1, "type": "int", "label": "点歌消耗"},
    "process_cost": {"env": "LOVKTV_PROCESS_COST", "default": 5, "type": "int", "label": "处理消耗"},
    "ad_reward": {"env": "LOVKTV_AD_REWARD", "default": 1, "type": "int", "label": "广告奖励"},
    "ad_seconds": {"env": "LOVKTV_AD_SECONDS", "default": 30, "type": "int", "label": "广告秒数"},
    "register_bonus": {"env": "LOVKTV_REGISTER_BONUS", "default": 10, "type": "int", "label": "注册奖励"},
    "download_bonus": {"env": "LOVKTV_DOWNLOAD_BONUS", "default": 10, "type": "int", "label": "下载奖励"},
    "ad_day_limit": {"env": "LOVKTV_AD_DAY_LIMIT", "default": 40, "type": "int", "label": "每日广告上限"},
    "ads_open": {"env": "LOVKTV_ADS_OPEN", "default": False, "type": "bool", "label": "允许广告外链"},
    "ads_json": {"env": "LOVKTV_ADS_JSON", "default": "", "type": "text", "label": "广告 JSON"},
    "ja_agent_enabled": {"env": "LOVKTV_JA_AGENT", "default": True, "type": "bool", "label": "启用日语注音"},
    "agent_url": {"env": "LOVKTV_AGENT_URL", "default": "", "type": "text", "label": "Agent 地址"},
    "agent_key": {"env": "LOVKTV_AGENT_KEY", "default": "", "type": "text", "label": "Agent Key", "secret": True},
    "agent_model": {"env": "LOVKTV_AGENT_MODEL", "default": "", "type": "text", "label": "Agent 模型"},
    "asr_model": {"env": "LOVKTV_ASR_MODEL", "default": "", "type": "text", "label": "语音识别模型"},
    "whisper_model": {"env": "LOVKTV_WHISPER_MODEL", "default": "small", "type": "text", "label": "Whisper 模型"},
    "whisper_compute_type": {"env": "LOVKTV_WHISPER_COMPUTE_TYPE", "default": "int8", "type": "text", "label": "Whisper 精度"},
    "https_proxy": {"env": "LOVKTV_HTTPS_PROXY", "default": "", "type": "text", "label": "外部 HTTPS 代理"},
    "public_url": {"env": "LOVKTV_PUBLIC_URL", "default": "", "type": "text", "label": "公网地址"},
    "asset_rev": {"env": "LOVKTV_ASSET_REV", "default": "", "type": "text", "label": "静态资源版本"},
}


def _coerce(key: str, value: Any) -> Any:
    spec = SETTINGS[key]
    kind = spec["type"]
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in _TRUE
    if kind == "int":
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return int(spec["default"])
    return str(value or "").strip()


def get(key: str) -> Any:
    if key not in SETTINGS:
        raise KeyError(key)
    try:
        with _connect() as conn:
            row = execute(conn, "SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    except Exception:
        # Read-only helpers may run before database initialization.
        row = None
    if row is not None:
        raw = row[0] if not isinstance(row, dict) else row.get("value")
        try:
            return _coerce(key, json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return _coerce(key, raw)
    return _coerce(key, os.environ.get(SETTINGS[key]["env"], SETTINGS[key]["default"]))


def set_value(key: str, value: Any) -> Any:
    if key not in SETTINGS:
        raise KeyError(key)
    value = _coerce(key, value)
    raw = json.dumps(value, ensure_ascii=False)
    now = int(time.time() * 1000)
    with _LOCK, _connect() as conn:
        execute(conn, "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (key, raw, now))
    return value


def catalog() -> list[dict[str, Any]]:
    try:
        with _connect() as conn:
            rows = execute(conn, "SELECT key FROM settings").fetchall()
    except Exception:
        rows = []
    stored = {str(row[0] if not isinstance(row, dict) else row.get("key")) for row in rows}
    return [
        {"key": key, "label": spec["label"], "type": spec["type"], "value": ("••••••" if spec.get("secret") and get(key) else get(key)), "secret": bool(spec.get("secret")), "source": "admin" if key in stored else "env"}
        for key, spec in SETTINGS.items()
    ]
