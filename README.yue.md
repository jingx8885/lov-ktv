# lov-ktv

[简体中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [粵語](README.yue.md)

一套畀屋企同私人房用嘅自託管 KTV。用手機掃碼搜歌、點歌，處理端會自動下載音訊、攞歌詞同分離人聲，再由電視或者瀏覽器播放同步掃色字幕。

[線上體驗](https://ktv.lovbrowser.com) · [電視端](https://ktv.lovbrowser.com/tv.html) · [手機點歌台](https://ktv.lovbrowser.com/m.html)

## 功能

- **搜歌入庫**：主要流程係搜歌名，唔使預先準備本地檔案；本地上載只係後備方法。
- **自動處理**：優先攞有時間標記嘅官方 LRC，用 ONNX Runtime 分離人聲同伴奏，唔需要 Torch 或者 openai-whisper。
- **多部裝置一齊用**：電視顯示房間 QR Code，手機掃碼之後就可以搜歌、點歌、頂歌、切歌同控制播放。
- **多種宿主**：支援瀏覽器電視端、Android TV 宿主同 Android 手機點歌台。
- **離線快取**：Android TV 會保存處理好嘅歌曲，處理端暫時離線都照樣唱到。
- **彈性儲存**：預設用 SQLite 同本地媒體目錄，亦可以設定 PostgreSQL 同阿里雲 OSS。

## 運作方式

```text
手機 / 點歌台  ── 搜歌、點歌、控制 ──▶  lov-ktv 處理端
       │                                  │
       │                                  ├─ 攞音源同 LRC
       │                                  ├─ ONNX 人聲分離
       │                                  └─ 儲存成品同歌詞
       │                                               │
       └──────────── 掃 QR Code 入房 ─────▶  電視 / 瀏覽器播放
```

搜歌流程會順序試網易雲試聽、SoundCloud 同 YouTube。歌詞會優先用官方 LRC，所以就算冇語音辨識服務都可以正常唱歌。

## 快速開始

### Docker Compose（建議）

需要先裝 Docker 同 Docker Compose。

```bash
git clone https://github.com/jingx8885/lov-ktv.git
cd lov-ktv
cp .env.example .env
docker compose up -d --build
```

開好之後可以去：

- 電視端：<http://localhost:8787/tv.html>
- 手機端：<http://localhost:8787/m.html>
- 服務狀態：<http://localhost:8787/api/host>

區域網入面嘅電視同手機，要將 `localhost` 換成運行 lov-ktv 嗰部電腦或者 NAS 嘅地址。`/api/host` 回傳嘅 `models.separator` 應該係 `true`。

### 本地 Python

需要 Python 3.11 或以上；完整嘅搜歌後備流程仲需要 FFmpeg 同 yt-dlp。

```bash
python -m venv .venv
# Linux / macOS
.venv/bin/pip install -e backend
PYTHONPATH=backend .venv/bin/uvicorn lovktv.main:app --host 0.0.0.0 --port 8787
```

Windows PowerShell 可以行 `.venv\Scripts\python -m pip install -e backend`，之後設定 `PYTHONPATH=backend` 再啟動 Uvicorn。

## Android App

- [Android TV](android-tv/README.md)：電視區域網宿主、成品快取，同埋接收手機傳過嚟嘅低延遲 UDP 咪高峰音訊。
- [Android 手機](android-phone/README.md)：原生點歌、播放控制，同埋將低延遲咪高峰音訊傳去電視。

手機網頁版一樣可以點歌，但低延遲咪高峰功能需要 Android 手機端同 Android TV 端一齊用。

## 設定

複製 `.env.example` 做 `.env`，再按需要填資料。所有整合都係選用：冇設定資料庫就會用 `data/lovktv.sqlite`，冇設定物件儲存就會用 `data/media`。

| 設定 | 用途 |
| --- | --- |
| `LOVKTV_PUBLIC_URL` | 公網地址同 OAuth 回調基址 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信開放平台登入 |
| `WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET` | 微信公眾號入面快捷登入 |
| `LOVKTV_DATABASE_URL` | PostgreSQL 連線字串 |
| `ALIYUN_OSS_*` | 用阿里雲 OSS 儲存處理好嘅媒體 |
| `LOVKTV_HTTPS_PROXY` | 淨係畀網易試聽 / yt-dlp 下載用嘅 HTTPS 代理 |

唔好提交 `.env`、密鑰、`data/`、歌庫或者編譯好嘅 APK。

## 項目文件

- [產品需求](docs/SPEC.md)
- [Epic / Issue 圖譜](docs/GRAPH.md)
- [API 說明](docs/api.md)
- [資料模型](docs/schema.md)

## 版權同授權

本項目嘅原創程式碼用 [Apache License 2.0](LICENSE) 授權。

第三方依賴、參考項目同 `vendor/` 入面嘅內容，各自跟返佢哋嘅授權條款；lovjpn 用 PolyForm Noncommercial 授權。歌曲、歌詞、封面同影片嘅權利屬於各自嘅權利人。使用者要確保部署同使用媒體嘅方式符合當地法律同內容平台條款，唔好公開發放未經授權嘅歌庫。
