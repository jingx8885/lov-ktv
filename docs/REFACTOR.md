# lov-ktv 架构重构需求与跟踪

> 重构批次标识：`R5-2026.08.29-supervisor-01`
>
> 本标识用于串联本轮监工会话、子会话提交与验收记录；后续批次递增末尾序号。

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

### R4 存储模块拆分 — 已完成

- [x] 建立独立 `room_store.py` 适配器，房间服务不再持有 SQLite 实现。
- [x] 将房间 SQL、队列、混音和 LAN 元数据迁入 `room_store.py`。
- [x] `lovktv.store` 仅保留无 SQL 的迁移导出，业务调用方改用 `room_store`。
- [x] 验收：事务边界和现有 schema 不变，房间/LAN/schema 回归通过（23 项）。

### R5 播放协议与前端状态 — 进行中

- [x] 固化后端房间 action 和 snapshot 字段契约（`contracts.py`）。
- [x] 在前端类型层补齐房间命令和歌词 timeline 字段。
- [x] 增加房间 code、action、暂停值的运行时规范化（`room_contract.py`）。
- [x] 增加歌词 timeline 的运行时校验和时间边界修复（`timeline_contract.py`）。
- [x] 固化播放控制事件的运行时校验，并在 WebSocket 入口接入。
- [x] 手机端房间 snapshot 读取和 stamp 提取到独立 `room/state.js`。
- [x] 手机端播放顺序决策提取到独立 `player/state.js`。
- [x] 电视端播放结束判断、房间条目身份和媒体重载决策提取到独立 `tv/playback/js/state.js`。
- [x] 电视端房间 WebSocket 重连和 snapshot 读取提取到独立 `tv/playback/js/room-state.js`。
- [x] 电视端 `LovKtvNative` MTV/歌词/设置能力集中到 `tv/platform.js` adapter。
- [ ] 前端按 `api / room-state / playback` 继续拆分状态，减少动态全局对象。
- [ ] 验收：TypeScript 检查不再新增错误，电视和手机各有协议 smoke test。

### R5A 前端平台边界与 DOM contract — 待开始

- [x] 本批次先为 `m.html`、`tv.html` 增加稳定 `data-app` / `data-mount` 挂载点，并加入静态启动 smoke test。
- [ ] 定义 `Platform`、`HttpPort`、`MediaPort`、`MicPort`、`RemotePort`、`ScannerPort`，浏览器 / Android Phone / Android TV 各有 adapter。
- [ ] 原生桥调用和回调集中到 adapter；业务模块不再直接访问 `window.LovKtvNative`、`window.LovKtvPhone`、`window.LovMic`、`window.LovAec`。
- [x] `m.html`、`tv.html` 建立必需节点清单和静态启动 smoke test。
- [ ] 功能模块改成 `mount(root, deps)`，降低 `$must()` 和全局 DOM id 耦合。
- [ ] Android Phone 注入入口改用稳定 data attribute / mount point，不再依赖 `.sheet`、`.lang-picker` 等视觉选择器。
- [ ] 验收：无原生桥、能力缺失、LAN 不可达时页面均能局部降级，不出现整页启动异常。

### R5B TV 播放运行时收敛 — 待开始

- [x] 本批次从 `tv.html` 移除 classic `boot-play.js` 入口，播放统一由 module `tv/app.js` 接管；保留文件以兼容直接访问。
- [ ] module 播放器稳定后删除 `tv/boot-play.js` 的 classic fallback、重复 timer 和第二套 `LovKtvRemote`。
- [ ] 播放、歌词、MTV、恢复、预取通过单一 controller / 事件协作，`tick.js` 不再承担所有生命周期职责。
- [ ] 验收：浏览器 TV 与 TV APK 只走同一播放路径，覆盖冷启动、暂停恢复、切歌、卡顿恢复和 MTV 降级。

### R5C shared 资源与类型边界 — 待开始

- [x] 本批次移除 `timeline.js` 的 TypeScript 排除项，单文件 `tsc` 检查通过。
- [ ] `stage-fx.js`、`timeline.js` 改为 ESM，Phone 学习模式不再从 `tv/` 目录加载资源。
- [ ] shared 模块禁止反向依赖 phone/tv；原生桥、内部事件、`LovI18n` 和 API 返回模型补齐类型声明。
- [ ] 将上述脚本纳入 TypeScript 检查，清空现有 bridge / `Song.song_id` / 学习状态漂移错误。
- [ ] 验收：`npm run check` 绿色，且 phone/tv 入口各有独立模块加载测试。

### R5D Web / embedded 资产一致性 — 待开始

- [ ] 一次构建生成 `frontend-dist` 和 `manifest.json`，后端静态服务与 Android TV APK 复用同一份产物。
- [ ] asset revision 改用 git commit/content hash，统一公网与 TV 内嵌资源的缓存语义。
- [ ] 增加公网文件与 TV 内嵌文件的路径、hash、入口 smoke test，防止 TV APK 提供旧版 `m.html`。
- [ ] 验收：同一发布 commit 下，公网 TV、TV APK TV 页、TV APK 提供的 Phone 页三者资源版本一致。

### R6 生命周期与部署 — 待开始

- [ ] 将 FastAPI startup 迁移到 lifespan，统一 worker 启停和健康检查。
- [ ] CI/本地测试命令固定使用项目 `.venv` 和 lock 文件。
- [ ] 验收：公网落地页、`/api/host`、`/tv.html`、`/m.html` 全部通过。

## 当前跟进

当前批次（`R5-2026.08.29-supervisor-01`）已完成 R5 前置的房间/播放状态拆分、TV 原生桥集中和前端运行时类型补齐，并落地三条并行支线的首个小步骤：

- R5A：平台能力与页面 DOM contract（先补稳定 mount point 和启动 smoke test）。
- R5B：TV 播放运行时收敛（清理 classic fallback，统一 module 播放路径）。
- R5C：shared 资源与类型边界（已先将 `timeline.js` 纳入 TypeScript 检查）。

本批次新增验收：`backend/tests/test_frontend_dom_contract.py`（2 项）及 TV 播放入口回归断言（1 项）。完整 `npm run check` 仍有既有 bridge / API 类型错误，需在后续 R5C 批次清理；不得将该基线失败误判为本批次回归。
