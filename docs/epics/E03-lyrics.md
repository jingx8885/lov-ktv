# E03 · 中日英歌词与 KTV 字幕

目标：已知歌词强制对齐到人声时间轴，输出可扫色的 KTV 字幕。

## Issues

- I06 歌词获取（粘贴 / LRCLIB / 转写）
- I07 CJK-first 强制对齐
- I08 ASS / Enhanced LRC / JSON 字幕

## 汇总验收

- 中文、日文按字输出时间戳；英文按词。
- 日文行带假名 reading。
- 生成 `lyrics.ass`、`lyrics.elrc`、`lyrics.json`，电视端只读 JSON/ELRC，不烧录视频。
- Whisper 转写不得覆盖用户粘贴的正文。
