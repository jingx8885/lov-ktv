# I05 · 双音轨封装与媒体网关

Epic: E02  
depends_on: I03, I04

## 合同

FFmpeg 产出：
- `instrumental.wav` / `vocals.wav`
- `karaoke.m4a`（伴奏主播放）
- `guide.m4a`（人声导唱，电视混音）
- 可选静帧或封面循环 `visual.mp4`

`GET /media/{song_id}/{file}` 带 CORS，供 TV 播放。

## 验收

- 缺 ffmpeg 时 job 失败原因可读。
- 媒体 URL 不暴露 data 根目录遍历。
