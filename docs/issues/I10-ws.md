# I10 · WebSocket 实时同步

Epic: E04  
depends_on: I09

## 合同

`/ws/rooms/{code}` 推送 snapshot：queue、now_playing、vocal_mix、volume、progress。  
电视定期上报 progress；控制命令广播。

## 验收

- 重连后立刻收到完整 snapshot。
- 非法命令返回 error 事件，不拆房间。
