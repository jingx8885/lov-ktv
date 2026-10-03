# 推广发帖文案（Launch Posts）

冷启动推广用。所有英文稿发布前按当天实际情况微调；统一口径：
**开源 + 自托管是主叙事，hosted demo 只是体验入口，收费仅覆盖处理算力。**

硬性事实（写作时已核对）：
- 仓库：https://github.com/jingx8885/lov-ktv ，License: Apache-2.0
- Demo: https://ktv.lovbrowser.com （TV: /tv.html ，手机: /m.html ，状态: /api/host）
- 定价：免费 20 首/月 · 入门 $5/月 = 100 首、标准队列、1 房间 · 畅唱 $20/月 = 1000 首、优先队列、5 房间
- 技术：Python 3.11+/FastAPI、ONNX Runtime 人声分离（纯 CPU）、faster-whisper（无 Torch）、yt-dlp 下载、SQLite 默认（PostgreSQL/OSS 可选）、Docker Compose 一键起、端口 8787
- 搜歌链路：NetEase 试听 → SoundCloud → YouTube；歌词优先官方 LRC
- Android：TV 宿主 App（成品离线缓存）+ 手机 App（UDP 低延时麦克风）

风险红线：
- 不承诺"无限免费处理"；hosted 规则一律按 docs/BILLING.md 表述
- 被问版权时不防御、不躲闪：按下方"备答点"口径回应
- 发帖别带投票请求（HN/Reddit/PH 都会删）

---

## 0. 发布前检查清单（主 agent / 上线前逐项过）

- [ ] demo 链路：注册 → 搜歌 → 处理完成 → 开唱 < 5 分钟，免费额度可用
- [ ] landing 页英文默认可达（或 navigator.language 检测生效）；og:title/og:image 有英文
- [ ] Stripe live 链路 E2E：checkout → webhook → 额度生效 → Customer Portal 退订
- [ ] terms/privacy 页面含 DMCA / takedown 联系入口（abuse 邮箱）
- [ ] 录制 demo GIF/视频（见第 6 节素材清单）
- [ ] 高峰预案：免费队列优先级为 0，被刷榜时限流或临时扩容器

---

## 1. Show HN

### Title（≤80 字符，选 1）

- 首选：`Show HN: Lov-ktv, self-hosted karaoke — search a song and sing it minutes later`
- 备选：`Show HN: Self-hosted karaoke that turns a song search into a singable track`

### 正文（提交时贴在文字框，链接填 GitHub 或 demo；建议链接填 https://github.com/jingx8885/lov-ktv）

I built lov-ktv because home karaoke always meant one of two bad options: buy a karaoke box with a fixed, aging song catalog, or hunt down instrumental versions and lyric files by hand for every song.

The flow: the TV (or a browser tab) shows a room QR code. Guests scan it from their phones, search a song by title, and queue it. The server then does everything in the background — fetches the audio (NetEase previews, SoundCloud, then YouTube via yt-dlp), grabs official timestamped LRC lyrics when they exist, separates vocals from accompaniment with ONNX Runtime (CPU only), and runs a no-Torch faster-whisper build for word-level lyric timing. The TV plays the backing track with scrolling, color-swept lyrics. A song is processed once and cached; upload is a fallback if you already have files.

Stack: Python/FastAPI, SQLite by default (Postgres and Alibaba OSS optional), plain HTML/JS frontends, Docker Compose for deploy. There are also native Android clients — a TV host app that caches finished songs, and a phone app that doubles as a low-latency wireless mic over UDP.

It's Apache-2.0 and fully self-hostable — `docker compose up -d --build` gives you a working room on any box/NAS. If you want to try the flow first, there's a hosted demo at https://ktv.lovbrowser.com (I charge a subscription for processing quota there to cover CPU time; self-hosting has no quota).

Happy to go deep on the vocal separation + lyric alignment pipeline — that was the fun part.

### 备答点（评论区高频问题）

- **版权**：The software is a self-hosted processing pipeline; audio sources are whatever the operator's fallback chain reaches (licensed preview endpoints first, then SoundCloud/YouTube). On the hosted demo, processed songs are stored per-account and there's a takedown path in the terms. Not a redistributor — same legal posture as yt-dlp-based media tools.
- **为什么不直接用现成 vocal remover**：分离只是管线的一段；卖点是"搜歌名→能唱"的端到端体验和多人房间。
- **处理时长**：每首次数分钟（纯 CPU 异步任务），处理完缓存，同一首歌只处理一次；付费档只是队列优先级和月度额度不同。
- **为什么默认 SQLite**：家庭单盒部署，一台 NAS 就够；Postgres 留给出量场景。

---

## 2. r/selfhosted

### Title

`lov-ktv — self-hosted karaoke: guests search & queue songs from their phones, the box does the rest (Docker, Apache-2.0)`

### Body

Hey r/selfhosted — I built **lov-ktv**, a self-hosted karaoke system for living rooms and party rooms.

The flow: the TV (or any browser) shows a room QR code. Guests scan it, search a song **by title** on their phones, and queue it. The server handles the rest in the background:

- pulls the audio (NetEase previews → SoundCloud → YouTube via yt-dlp)
- grabs official timestamped LRC lyrics when available
- separates vocals from accompaniment with ONNX Runtime — CPU only, no GPU needed
- word-level lyric timing via a no-Torch faster-whisper build
- plays the result on the TV with scrolling, color-swept lyrics

Songs are processed once and cached, so the party never re-processes. Local file upload is a fallback.

**Deploy**: clone, `cp .env.example .env`, `docker compose up -d --build`. Defaults are SQLite + local disk — runs fine on a NAS or mini PC. PostgreSQL and Alibaba Cloud OSS are optional. Open http://<host>:8787/tv.html on the TV and you're in business.

**Extras**: native Android TV host app (caches finished songs, so playback survives server downtime) and an Android phone app that doubles as a low-latency wireless mic over UDP. The web remote works without installing anything.

Links: [GitHub](https://github.com/jingx8885/lov-ktv) · [Live demo](https://ktv.lovbrowser.com) · Apache-2.0

Transparency: the repo is fully free and self-hostable with no limits. The hosted demo charges a subscription for processing quota to cover CPU time — that's the whole business model, no data sale, no ads.

Happy to answer questions — the vocal-separation/lyric-alignment pipeline was the fun part to build.

---

## 3. r/karaoke

### Title

`I built a karaoke system where you just search a song name — it builds the sing-along track itself`

### Body

I got tired of the usual home-karaoke tradeoffs: karaoke machines with stale catalogs, YouTube "instrumental" rips with vocals bleeding through, and lyric files that never sync.

So I built lov-ktv. The TV shows a QR code, everyone joins from their phones, searches a song by title, and queues it. A few minutes later it's playing: vocals removed, lyrics synced and sweeping across the screen like a real KTV box. Once a song is processed it's cached, so repeat songs are instant.

It's open source and self-hosted (Apache-2.0, runs on a NAS/mini PC with one Docker command), and there's a hosted version at https://ktv.lovbrowser.com if you don't want to run a server. There are also Android apps — the TV app keeps a local cache, and the phone app can act as a wireless mic.

Would love feedback from people who actually run karaoke nights — what's the feature that would make you switch?

---

## 4. Product Hunt

（建议放在社区帖之后 1–2 周，等 GitHub star 积累和 bug 修复；发布日选周二/三/四，太平洋时间 00:01 起跑。）

- **Name**: lov-ktv
- **Tagline**（≤60 字符）: `Self-hosted karaoke: search a song, sing it minutes later`
- **Topics**: Open Source · Music · Home Entertainment
- **Description**（≤260 字符）:

  `Turn a song search into a karaoke track. lov-ktv fetches audio, strips vocals with ONNX, aligns lyrics word-by-word, and plays on your TV — guests queue from their phones via QR code. Apache-2.0, one Docker command, hosted demo included.`

- **Maker first comment**:

  Hey PH! I built lov-ktv after too many party nights fighting with karaoke machines that didn't have the songs we wanted.

  It works like a jukebox that builds itself: TV shows a QR code, guests search a song title on their phones, and the server handles the rest — fetching audio, separating vocals with ONNX Runtime, aligning lyrics word-by-word with faster-whisper, then playing it all on the TV with that classic color-sweep karaoke look.

  Fully open source (Apache-2.0) and self-hostable with one Docker Compose command — runs on a NAS or a mini PC, CPU-only. If you just want to try it, the hosted demo is live. Would love your feedback, especially from anyone who's built audio pipelines before!

  GitHub: https://github.com/jingx8885/lov-ktv · Demo: https://ktv.lovbrowser.com

- **Gallery 素材清单**（制作时按序）:
  1. 30 秒 demo GIF：手机搜歌 → 队列 → 电视扫色字幕（最重要的一张）
  2. 房间 QR + 多部手机点歌界面并排截图
  3. 处理管线示意图（搜歌 → 分离 → 对齐 → 播放）
  4. tv.html 播放截图 + m.html 点歌台截图
  5. Docker 一键部署终端录屏

---

## 5. awesome-selfhosted PR

（周期长、先发；合并后给 GitHub 带稳定外链和 star。条目归属分类以仓库当时目录为准，候选：Media Streaming / Audio 或 Miscellaneous。）

### 条目

```text
- [lov-ktv](https://github.com/jingx8885/lov-ktv) - Self-hosted karaoke system: guests queue songs by title from their phones, the server fetches audio, removes vocals and aligns lyrics for TV playback. ([Demo](https://ktv.lovbrowser.com)) `Apache-2.0` `Python/Docker`
```

（PR 前按 awesome-selfhosted 的 CONTRIBUTING.md 校对该行格式。）

### PR 描述

Add lov-ktv — an Apache-2.0 self-hosted karaoke system for homes/party rooms.

- Search-first: guests queue songs by title from their phones; no media library to prepare.
- Automated pipeline: audio retrieval (NetEase/SoundCloud/YouTube via yt-dlp) → ONNX vocal separation (CPU-only) → faster-whisper word-level lyric alignment → synchronized TV playback.
- Documented one-command Docker Compose install; SQLite by default, PostgreSQL/OSS optional.
- Actively maintained, tagged releases, English README (README.en.md), live demo at https://ktv.lovbrowser.com.

---

## 6. 短视频脚本（30s，YouTube Shorts / TikTok / PH 视频共用）

| 时间 | 画面 | 字幕/旁白 |
| --- | --- | --- |
| 0–3s | 特写：手机上输入歌名搜索 | "Home karaoke without a karaoke machine." |
| 3–8s | 电视显示房间 QR，手机扫码进房 | "Scan. Search. Queue." |
| 8–15s | 服务器处理进度快速闪过（下载→人声分离→歌词对齐） | "It fetches the song, removes the vocals, syncs the lyrics — by itself." |
| 15–25s | 电视播放扫色字幕，朋友轮流用手机点歌、顶歌 | "Everyone queues from their own phone." |
| 25–30s | 落版 logo + 链接 | "lov-ktv · open source, self-hosted · ktv.lovbrowser.com" |

录制要点：真实设备拍（电视+手机同框最有说服力）；处理等待剪掉 2/3；结尾 URL 停留 ≥2s。

---

## 7. X / IndieHackers

### X 首帖（build in public，配 demo GIF）

Built a self-hosted karaoke box: TV shows a QR → guests search a song title on their phones → server strips vocals with ONNX, word-aligns lyrics with whisper, TV plays it like real KTV.

Apache-2.0, one `docker compose up`. Hosted demo if you just want to try: https://ktv.lovbrowser.com 🎤

### X 线程续帖（2–4）

2/ The pipeline: NetEase preview → SoundCloud → YouTube for audio; official LRC first; ONNX Runtime vocal separation (CPU only); faster-whisper for word timing; falls back to LRC/onset when ASR is out.

3/ There's an Android TV app that caches finished songs (parties survive server downtime) and a phone app that's a low-latency wireless mic over UDP.

4/ Business model: self-host free forever; hosted version charges for processing quota ($5/$20 mo) because vocal separation eats CPU. That's it — no ads, no data.

### IndieHackers（等首批付费用户后更有料，先存草稿）

Show IH 风格：痛点 → 方案 → 自托管+hosted 混合模式 → 当前指标（留空待填）→ 求反馈。等 Show HN/PH 数据出来后再发，引用真实数字。

---

## 8. 发帖顺序与时间

1. **第 0 天**：awesome-selfhosted PR 提交（周期长，先排队）。
2. **第 1–2 天**：Show HN（美西工作日 8–10am PT）；当天盯评论区逐条回。
3. **第 3–4 天**：r/selfhosted（错开 HN，避免同一批人疲劳）；r/karaoke 再隔 2 天。
4. **第 5–14 天**：按反馈修 bug、补 landing demo 素材；X 持续 build in public。
5. **第 15 天左右**：Product Hunt（周二/三/四 PT 00:01），此时已有 GitHub star 和真实用户反馈做信任背书。

所有帖子统一引流顺序：demo（即玩）→ GitHub（沉淀 star）→ billing（转化）。
