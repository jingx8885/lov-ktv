# E07 · 部署与联调验收

目标：一条命令拉起全栈，中日英各一首能走完。

## Issues

- I14 Compose 一键启动
- I15 中日英端到端验收脚本

## 汇总验收

- `docker compose up --build` 后打开 `/tv` 与 `/m`。
- `scripts/accept.sh` 对 zh/ja/en fixture 跑通对齐与字幕，不依赖真实商业音频。
