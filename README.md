# lov-ktv

家庭 / 包厢 KTV：手机**搜歌名入库**（不是先上传文件），服务器做人声分离和中日英扫色字幕，Android TV / 浏览器电视端播放。

搜歌下载逻辑来自 [lovjpn](https://github.com/jingx8885/lovjpn) 的 `fetch_song.py`：

1. tonzhon.com 搜网易云  
2. 拉带时间戳的 LRC  
3. 音频：网易外链 → yt-dlp SoundCloud → YouTube  

本地选文件上传只是后备。

## 启动

```bash
cd /Users/yesone/project/lov-ktv
python3 -m venv .venv
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --project backend --extra dev --frozen
# 搜歌回落需要：
# brew install ffmpeg yt-dlp
PYTHONPATH=backend .venv/bin/uvicorn lovktv.main:app --host 0.0.0.0 --port 8787
```

- 电视：http://本机:8787/tv.html  
- 手机：扫电视二维码，或打开 http://本机:8787/m.html?room=房间码  
- 登录：http://本机:8787/login.html  

微信登录（可选）环境变量：`WECHAT_APP_ID`、`WECHAT_APP_SECRET`；微信内快捷登录再配 `WECHAT_MP_APP_ID`、`WECHAT_MP_APP_SECRET`；公网回调 `LOVKTV_PUBLIC_URL`。没配微信时，手机可用本机身份，电视出二维码给手机确认。

Android TV：用 Android Studio 打开 `android-tv/`。安装后 App 在电视上开局域网服务，并收手机 UDP 麦；首次填处理服务器 `http://电脑IP:8787`。说明见 `android-tv/README.md`。

Android 点歌台：用 Android Studio 打开 `android-phone/`。点歌走 HTTP；低延时麦发到同一 WiFi 上的电视 App。网页 `m.html` 仍可用，但不走 UDP 麦。说明见 `android-phone/README.md`。

Docker（处理端发版）：

```bash
cp .env.example .env   # 可选：微信 / 日语注音
docker compose up --build -d
```

健康检查：http://本机:8787/api/host  
`/api/host` 的 `models.separator` 应为 true（镜像已烤入 UVR ONNX，走 onnxruntime，不装 Torch）。歌词对齐优先用官方 LRC。  
电视 App 填：`http://电脑或 NAS 的局域网IP:8787`

本地验收：`scripts/accept.sh` 使用仓库根目录 `.venv` 和锁定的 `backend/uv.lock`；公网验收可运行
`.venv/bin/python scripts/accept-production.py --base https://ktv.lovbrowser.com`。

公网（`ktv.lovbrowser.com`，43 上只绑 `127.0.0.1:8790`）：

```bash
cp .env.example .env
# LOVKTV_PUBLIC_URL=https://ktv.lovbrowser.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
sudo cp deploy/nginx/ktv.lovbrowser.com.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/ktv.lovbrowser.com.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

对照仓库：

```bash
scripts/fetch-vendors.sh
```

## 文档

- 需求合同：`docs/SPEC.md`
- Epic / Issue 图谱：`docs/GRAPH.md`
- 搜歌主路：`docs/issues/I03-upload.md`

## 版权

仅供个人或家庭局域网。不要公开发布 `data/media`。lovjpn 为 PolyForm Noncommercial。
