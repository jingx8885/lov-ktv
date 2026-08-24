# vendor 对照仓库

由 `scripts/fetch-vendors.sh` 浅克隆，不打进发行镜像。

| 目录 | 用途 |
|---|---|
| `lovjpn` | **搜歌 / 下载 / LRC 主逻辑**（tonzhon + 网易外链 + yt-dlp） |
| `ktv-home` / `home-ktv-system` | Android TV + 点歌队列对照 |
| `python-audio-separator` | 人声分离 |
| `lyric-align` / `nicokara-studio` | 中日英对齐与日语注音对照 |
| `nightingale` / `OpenKara` | AI Karaoke 体验对照 |

`lovjpn` 许可证为 PolyForm Noncommercial。lov-ktv 的 `catalog/fetch.py` 按同一套协议重写，供个人/家庭局域网使用。
