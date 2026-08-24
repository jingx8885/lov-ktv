# I07 · CJK-first 强制对齐

Epic: E03  
depends_on: I06

## 合同

已知歌词锚定到 ASR/onset 时间：
- zh/ja：字级
- en：词级
- ja：pykakasi 假名
- 中英/日英混排按行处理，不按语言拆两次推理

无 ASR 时按行均分歌曲时长，仍输出完整 timeline（可唱，精度降级并标记）。

## 验收

- 单测覆盖中日英三行 fixture，时间单调、覆盖全文。
- 英文不得用 CJK 过低阈值误匹配。
