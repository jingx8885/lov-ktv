# SPEC-001 · lov-ktv

状态：active  
产品名：lov-ktv  
日期：2026-08-24

## 目标

自托管家庭 / 包厢 KTV：手机搜歌名入库（lovjpn 搜索下载逻辑），服务器做人声分离并生成中日英 KTV 字幕，Android TV 播放伴奏、扫色歌词，并支持原唱/伴唱切换、点歌队列和扫码进房。

验收以真实搜歌入库、真实处理产物、电视端可唱为准。手机选文件上传只是后备。

## 范围内

1. **主路径：搜索下载。** 按 [lovjpn](https://github.com/jingx8885/lovjpn) 的 `fetch_song.py`：tonzhon.com 搜网易云 → 拉 LRC → 音频 网易外链 → SoundCloud → YouTube。
2. 本地上传只作后备（自有文件 / 下载失败）。
3. 服务器做人声分离，产出伴奏 + 人声 + 双音轨。
4. 歌词：tonzhon/网易 LRC 优先；粘贴次之；再否则转写。
5. 中 / 日 / 英：中日字级扫色，英文词级扫色；日语附假名注音。
6. 输出 Enhanced LRC、ASS `\k`、JSON timeline，字幕外挂不烧录。
7. 手机端：搜歌、点歌、顶歌、切歌、原伴唱、音量；上传收进次级入口。
8. Android TV：10 尺界面、队列、二维码、双音轨、当前句+下一句扫色。
9. Web TV 与 APK（WebView）共用播放页。

## 非目标

- 不运营公网曲库，不把下载结果二次分发到公网。
- 第一期不做评分、升降调、蓝牙麦混音、多房间计费。
- 不承诺 AI 伴奏达到官方母带。
- 不把 lovjpn 的学习页 / TTS 拆解做成电视主体验。

## 关键决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 仓库名 | lov-ktv | 用户指定 |
| 进曲 | lovjpn / tonzhon 搜索下载 | 手机上传体验差，用户通常没有文件 |
| 后端 | Python FastAPI + SQLite | 直接调用分离/对齐生态 |
| 分离 | audio-separator（UVR / BS-RoFormer / KARA_2） | 生产级、MIT |
| 对齐 | 网易 LRC 行级时间戳 + 行内字/词插值 | 官方 LRC 比 Whisper 稳 |
| 播放 | Web TV + Android TV WebView | H.264/AAC 产物，一套 UI |
| 协议 | 房间码 + WebSocket | 手机与电视实时同步 |
| 参考 | `vendor/lovjpn` 及其它浅克隆 | 搜索下载逻辑以 lovjpn 为准 |

## 最终验收

1. 用搜歌入库走通中 / 日 / 英各一首（tonzhon 可达时），均有伴奏、人声、ASS/LRC/JSON。
2. 手机扫电视二维码进同一房间，点歌后电视自动开唱。
3. 电视显示当前句扫色 + 下一句预览；中日按字，英文按词。
4. 原唱/伴唱切换不中断画面。
5. 日语歌词显示假名注音。
6. `docker compose up` 后本地可完整走通。
7. Android TV APK 能打开播放页并保持 Leanback 启动器图标。

## 版权边界

搜歌下载仅供个人/家庭局域网学唱。禁止把 `data/media` 公开发布。仓库不得包含商业歌曲样例。
