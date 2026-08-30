# E07 · 部署与联调验收

目标：一条命令拉起全栈，中日英各一首能走完。

## Issues

- I14 Compose 一键启动
- I15 中日英端到端验收脚本

## 汇总验收

- `docker compose up --build` 后打开 `/tv` 与 `/m`。
- `scripts/accept.sh` 对 zh/ja/en fixture 跑通对齐与字幕，不依赖真实商业音频。
- 生产发布必须重建 `base` 层（含 ONNX 与 faster-whisper small 模型），并从 43 上运行：
  `python3 scripts/accept-production.py --expect-origin https://ktv.lovbrowser.com --require-whisper`。
- 公网验收要求 `/api/host` 的 `models.separator` 与 `models.whisper` 均为 `true`；再对目标歌曲执行重新对齐并确认 `lyrics.json` 的 `alignment_source` 为 `whisper` 或 `agent+whisper`。
