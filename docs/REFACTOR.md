# lov-ktv 架构重构需求与跟踪

## 目标

让“搜歌、处理、房间、播放端、部署”通过稳定边界协作，修改单一功能时不需要同时改多个传输层或全局状态。重构期间保持现有 API、房间协议和媒体目录兼容。

## 约束

- 不改变公网 API 路径和现有房间 WebSocket 消息格式，除非同时提供兼容期。
- 不把曲库、`data/`、`.env`、模型或 APK 纳入 git/镜像。
- 每个阶段必须有针对性测试；完整测试中的环境失败要单独记录。
- 生产仍使用 SQLite + 当前 Compose，先做边界隔离，再考虑替换存储。

## 阶段与验收

### R0 基线与分支保护 — 已完成

- [x] 架构分支从最新 `origin/master` rebase。
- [x] 记录当前测试和未跟踪用户文件，不做清理性操作。

### R1 房间领域服务 — 已完成

- [x] REST、WebSocket 共用 `RoomService` 命令入口。
- [x] 房间服务依赖 `RoomRepository`，SQLite 通过适配器接入。
- [x] 房间命令 payload 有统一模型和隔离测试。

### R2 后台任务生命周期 — 已完成

- [x] 全局队列、锁、worker 状态收进 `JobQueue`。
- [x] 保留 `spawn()` 兼容入口，重复任务只在 pending 期间去重。

### R3 歌曲/任务持久化边界 — 已完成

- [x] 从 `jobs.py` 移除对 `store` 函数的散落直接调用，增加 `SongRepository` 接口。
- [x] 将恢复任务逻辑变成可注入的 `JobRecovery`，不依赖模块级全局。
- [ ] 验收：任务处理和恢复测试可使用 fake repository，不需要 SQLite。

### R4 存储模块拆分 — 待开始

- [x] 建立独立 `room_store.py` 适配器，房间服务不再持有 SQLite 实现。
- [ ] 将 `store.py` 按歌曲、房间、账号/宿主、任务拆成内部模块。
- [ ] 保留 `lovktv.store` 兼容导出，分阶段迁移调用方。
- [ ] 验收：事务边界和现有 schema 不变，房间并发回归通过。

### R5 播放协议与前端状态 — 待开始

- [ ] 固化房间 snapshot、播放控制、歌词 timeline 的共享字段定义。
- [ ] 前端按 `api / room-state / playback` 拆分状态，减少动态全局对象。
- [ ] 验收：TypeScript 检查不再新增错误，电视和手机各有协议 smoke test。

### R6 生命周期与部署 — 待开始

- [ ] 将 FastAPI startup 迁移到 lifespan，统一 worker 启停和健康检查。
- [ ] CI/本地测试命令固定使用项目 `.venv` 和 lock 文件。
- [ ] 验收：公网落地页、`/api/host`、`/tv.html`、`/m.html` 全部通过。

## 当前跟进

下一项是 R4：把 `store.py` 的房间 SQL 迁入 `room_store.py`，同时保留 `lovktv.store` 兼容导出；每完成一个可回滚的小步骤就更新本文件并提交。
