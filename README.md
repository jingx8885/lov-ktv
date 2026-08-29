# lov-ktv

[简体中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [粵語](README.yue.md)

自托管的家庭 / 包厢 KTV：手机扫码搜歌点歌，处理端自动下载音频、获取歌词并分离人声，电视或浏览器负责播放和扫色字幕。

[在线体验](https://ktv.lovbrowser.com) · [电视端](https://ktv.lovbrowser.com/tv.html) · [手机点歌台](https://ktv.lovbrowser.com/m.html)

## 功能

- **搜歌入库**：主流程是搜索歌名，不需要先准备本地文件；本地上传仅作后备。
- **自动处理**：优先获取带时间戳的官方 LRC，使用 ONNX Runtime 完成人声 / 伴奏分离，无需 Torch 或 openai-whisper。
- **多端协作**：电视显示房间二维码，手机扫码后即可搜歌、点歌、顶歌、切歌和控制播放。
- **多种宿主**：支持浏览器电视端、Android TV 宿主和 Android 手机点歌台。
- **离线缓存**：Android TV 可缓存处理完成的歌曲，处理端暂时离线时仍能播放。
- **灵活存储**：默认使用 SQLite 和本地媒体目录，也可配置 PostgreSQL 与阿里云 OSS。

## 工作方式

```text
手机 / 点歌台  ── 搜歌、点歌、控制 ──▶  lov-ktv 处理端
       │                                  │
       │                                  ├─ 音源与 LRC 获取
       │                                  ├─ ONNX 人声分离
       │                                  └─ 成品与歌词存储
       │                                               │
       └──────────── 扫码进入房间 ────────▶  电视 / 浏览器播放
```

搜歌链路依次尝试网易云试听、SoundCloud 和 YouTube。歌词优先使用官方 LRC，因此即使没有语音识别服务也可以正常演唱。

## 快速开始

### Docker Compose（推荐）

需要安装 Docker 与 Docker Compose。

```bash
git clone https://github.com/jingx8885/lov-ktv.git
cd lov-ktv
cp .env.example .env
docker compose up -d --build
```

启动后打开：

- 电视端：<http://localhost:8787/tv.html>
- 手机端：<http://localhost:8787/m.html>
- 服务状态：<http://localhost:8787/api/host>

局域网中的电视和手机请将 `localhost` 换成运行 lov-ktv 的电脑或 NAS 地址。`/api/host` 返回的 `models.separator` 应为 `true`。

### 本地 Python

需要 Python 3.11+；完整的搜歌回落链路还需要 FFmpeg 和 yt-dlp。

```bash
python -m venv .venv
# Linux / macOS
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --project backend --extra dev --frozen
# 搜歌回落需要：
# brew install ffmpeg yt-dlp
PYTHONPATH=backend .venv/bin/uvicorn lovktv.main:app --host 0.0.0.0 --port 8787
```

Windows PowerShell 可使用 `.venv\Scripts\python -m pip install -e backend`，然后设置 `PYTHONPATH=backend` 并启动 Uvicorn。

## Android 客户端

- [Android TV](android-tv/README.md)：电视局域网宿主、成品缓存，以及接收手机低延时 UDP 麦克风。
- [Android 手机](android-phone/README.md)：原生点歌、播放控制，以及向电视发送低延时麦克风音频。

网页手机端同样可以点歌，但低延时麦克风功能需要同时使用 Android 手机端和 Android TV 端。

## 配置

复制 `.env.example` 后按需填写。所有配置均为可选项；未配置数据库时使用 `data/lovktv.sqlite`，未配置对象存储时使用 `data/media`。

| 配置 | 用途 |
| --- | --- |
| `LOVKTV_PUBLIC_URL` | 公网访问地址及 OAuth 回调基址 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信开放平台登录 |
| `WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET` | 微信公众号内快捷登录 |
| `LOVKTV_DATABASE_URL` | PostgreSQL 连接串 |
| `ALIYUN_OSS_*` | 阿里云 OSS 成品媒体存储 |
| `LOVKTV_HTTPS_PROXY` | 仅供网易试听 / yt-dlp 下载链路使用的 HTTPS 代理 |

不要提交 `.env`、密钥、`data/`、曲库或构建出的 APK。

本地验收：`scripts/accept.sh` 使用仓库根目录 `.venv` 和锁定的 `backend/uv.lock`；公网验收可运行
`.venv/bin/python scripts/accept-production.py --base https://ktv.lovbrowser.com`。

公网（`ktv.lovbrowser.com`，43 上只绑 `127.0.0.1:8790`）：

## 项目文档

- [产品需求](docs/SPEC.md)
- [Epic / Issue 图谱](docs/GRAPH.md)
- [API 说明](docs/api.md)
- [数据模型](docs/schema.md)

## 版权与许可

本项目原创代码采用 [Apache License 2.0](LICENSE) 授权。

第三方依赖、参考项目及 `vendor/` 中的内容遵循各自的许可证；其中 lovjpn 使用 PolyForm Noncommercial 许可证。歌曲、歌词、封面和视频的权利归各自权利人所有。使用者应确保其部署与媒体使用方式符合所在地法律及内容平台条款，请勿将未经授权的曲库公开分发。
