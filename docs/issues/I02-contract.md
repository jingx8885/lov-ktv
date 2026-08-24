# I02 · 数据模型 / API 契约 / 媒体目录

Epic: E01  
depends_on: I01

## 合同

歌曲、任务、房间、队列项、歌词时间轴的字段一次定义，前后端共用 TypeScript/JSON 形态。  
媒体落在 `data/media/{song_id}/`。

## 验收

- OpenAPI 或 `docs/api.md` 覆盖上传、任务、曲库、房间、队列、媒体。
- 目录约定见 README。
