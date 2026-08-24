# I15 · 中日英端到端验收脚本

Epic: E07  
depends_on: I14, I13

## 合同

`scripts/accept.sh` 用合成正弦波 + 固定歌词跑分离降级、对齐、字幕，不下载商业歌曲。

## 验收

- zh/ja/en 三组 fixture 退出码 0。
- 断言 timeline 语种、token 数、ASS `\k` 存在。
