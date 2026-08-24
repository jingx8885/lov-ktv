# I03 · 搜歌下载入库（主）与本地上传（备）

Epic: E02  
depends_on: I02  
对照：`vendor/lovjpn/scripts/fetch_song.py`、`vendor/lovjpn/SKILL.md`

## 合同

手机主路径是**搜索 + 一键入库**，不是选文件上传。

1. `GET /api/search?q=` 调 tonzhon `types=search&source=netease`，返回歌名/歌手/封面/id。
2. `POST /api/songs/import` 按 lovjpn 同一套回落：
   - 拉 LRC（`types=lyric`）
   - 网易 `outer/url?id=` 探测，跳过 302→/404
   - 失败则 yt-dlp SoundCloud，再 YouTube
   - 过滤 remix / off vocal / カラオケ / live / cover
3. `POST /api/songs` 仍接收本地文件，仅后备。

## 验收

- 搜索「YOASOBI 群青」或中文歌名能出候选（依赖 tonzhon 可达）。
- import 成功后目录里有 `original.mp3` 与 `lyrics.lrc`（或明确 `audio_source=none` + 仍有 LRC）。
- 标题过滤单测覆盖 カラオケ / off vocal 不会当原曲。
- 上传仍可用，但不作为手机首页主按钮。
