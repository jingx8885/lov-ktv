# lov-ktv 架构重构需求与跟踪

> 文档审计：2026-08-30（基于 `0ff3f2d`）。完成状态以当前 `master` 工作树和可重复的测试/构建命令为准；历史批次说明仅作追溯。

> 重构批次标识：`R5-2026.08.29-supervisor-02`
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
- [x] 验收：任务处理和恢复测试可使用 fake repository，不需要 SQLite。

证据：`backend/tests/test_jobs.py` 的 `test_song_repository_is_replaceable` 与 `test_job_recovery_accepts_repository_and_submitter` 分别替换歌曲仓储和恢复提交器；执行 `PYTHONPATH=backend python -m pytest -q backend/tests/test_jobs.py`（亦包含在本次全量回归中）。

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
- [x] 电视端播放结束判断、房间条目身份和媒体重载决策提取到独立 `tv/playback/js/runtime/state.js`。
- [x] 电视端房间 WebSocket 重连和 snapshot 读取提取到独立 `tv/playback/js/room/state.js`。
- [x] 电视端 `LovKtvNative` MTV/歌词/设置能力集中到 `tv/platform.js` adapter。
- [x] Phone 播放与房间模块分别归档到 `player/js/playback`、`room/js/room`，消除同级文件与二级目录混排。
- [x] 共享音频与舞台特效按 `aec`、`bands`、`rtc`、`fx/stage` 归档，Phone 不再反向依赖 TV 目录。
- [x] Phone/TV 入口提供 `mount(root, deps)` 生命周期边界；DOM 查询通过作用域化 `setDomRoot` 和本地节点解析器完成，入口不再直接依赖全局 `$must()`。
- [x] Phone 状态按 `catalog`、`room`、`player` 切片；TV 状态按 `room`、`playback`、`audio` 切片，根 `state` 仅保留将写入路由到 owner 的 facade。
- [x] 验收：TypeScript 检查不再新增错误，电视和手机各有协议 smoke test。

### R5A 前端平台边界与 DOM contract — 核心闭环已完成（本批）

- [x] 本批次先为 `m.html`、`tv.html` 增加稳定 `data-app` / `data-mount` 挂载点，并加入静态启动 smoke test。
- [x] 定义 Phone `Platform` 的 `http`、`media`、`mic`、`remote`、`scanner` ports；无桥浏览器和 Android Phone 共用同一降级 adapter，Android TV 保持独立 `tv/platform.js` adapter。
- [x] 原生桥调用和 LAN HTTP 回调集中到 `phone/platform.js`；Phone 业务模块不再直接访问注入桥，缺少能力时返回安全的 no-op / fallback。
- [x] `m.html`、`tv.html` 建立必需节点清单和静态启动 smoke test。
- [x] 功能模块改成 `mount(root, deps)`，降低 `$must()` 和全局 DOM id 耦合。
- [x] Android Phone 注入入口改用稳定 data attribute / mount point，不再依赖 `.sheet`、`.lang-picker` 等视觉选择器。
- [x] 验收：无原生桥、能力缺失、LAN 不可达时页面均能局部降级，不出现整页启动异常（静态契约测试覆盖）。

> 本批已完成入口 `mount(root, deps)` 边界；功能模块共享的 DOM 查询由 mount 设置作用域，后续可继续按模块收紧端口。其余 R5A adapter、桥隔离、LAN 回调、降级和 DOM contract 均已闭环并有测试。

### R5B TV 播放运行时收敛 — 已完成

- [x] 从 `tv.html` 移除 classic `boot-play.js` 与重复 `boot-qr.js` 入口，播放和房间初始化统一由 module `tv/app.js` 接管。
- [x] 删除 `tv/boot-play.js` 的 classic fallback、重复 timer 和第二套 `LovKtvRemote`，同步清理全局类型声明。
- [x] 播放、歌词、MTV、恢复、预取沿现有 module controller 协作，未改变 API、WebSocket 或媒体协议。
- [x] 静态验收覆盖浏览器 TV / TV APK 共用路径、冷启动、暂停恢复、切歌、卡顿恢复和 MTV 降级；TV 播放回归 3 项通过。

证据：`backend/tests/test_tv_playback.py`、`test_frontend_split.py` 覆盖 module 单入口、播放结束/恢复、房间快照和资源路径；执行 `PYTHONPATH=backend python -m pytest -q backend/tests/test_tv_playback.py backend/tests/test_frontend_split.py` 通过。

### R5C shared 资源与类型边界 — 已完成

- [x] 本批次移除 `timeline.js` 的 TypeScript 排除项，单文件 `tsc` 检查通过。
- [x] 舞台特效归档到 `shared/fx/js/stage`，Phone 学习模式与 TV 播放共用资源；播放器 timeline 归档到 `phone/player/js/playback`。
- [x] shared 模块禁止反向依赖 phone/tv；原生桥、内部事件、`LovI18n` 和 API 返回模型补齐类型声明。
- [x] 将上述脚本纳入 TypeScript 检查，清空现有 bridge / `Song.song_id` / 学习状态漂移错误。
- [x] 验收：`npm run check` 绿色，且 phone/tv 入口各有独立模块加载测试。

证据：`frontend/tsconfig.json` 已纳入 playback timeline 与 `shared/fx`；`backend/tests/test_frontend_types.py`、`test_stage_fx_split.py` 和 `test_frontend_split.py` 检查类型声明、反向依赖和入口路径。执行 `npm ci --ignore-scripts`、`npm run check`（tsc、ESLint、Prettier）通过。

### R5D Web / embedded 资产一致性 — 已完成（构建链闭环；真实 APK 对比留项）

- [x] 一次构建生成 `frontend-dist` 和 `manifest.json`，后端静态服务与 Android TV APK 复用同一份产物。
- [x] asset revision 使用内容 SHA-256（并记录 git commit），后端和 Android `AssetRev` 均从 manifest 读取。
- [x] 增加 `scripts/check-frontend-parity.py`，对 `frontend-dist/manifest.json`、TV APK `assets/web` 内嵌文件和公网 manifest/静态资源执行路径、hash、入口与 revision 对比；并加入合成 APK 回归测试。
- [ ] 验收：同一发布 commit 下，公网 TV、TV APK TV 页、TV APK 提供的 Phone 页三者资源版本一致（需真实 APK 产物）。

证据：`scripts/build-frontend-dist.py`、`scripts/check-frontend-parity.py`、`backend/lovktv/assets.py`、`android-tv/app/src/main/java/com/lovktv/tv/platform/AssetRev.kt` 形成单一 manifest/revision 链；`backend/tests/test_assets.py` 与 `backend/tests/test_frontend_parity.py` 覆盖 manifest、版本注入、路径/hash 对比和 web 产物入口。Android Gradle 任务 `copyWebAssets` 已依赖该构建脚本；真实 APK 与同 revision 公网产物仍需在发布机执行 parity 命令完成最终验收。

### R6 生命周期与部署 — 已完成

- [x] 将 FastAPI startup 迁移到 lifespan，统一 worker 启停和健康检查（`/healthz`）。
- [x] CI/本地测试命令固定使用项目 `.venv` 和 `backend/uv.lock`（`uv sync --frozen`）。
- [x] 增加公网验收脚本 `scripts/accept-production.py`，覆盖 `/`、`/api/host`、`/tv.html`、`/m.html`；本地生命周期 smoke test 同步覆盖。

### R7 后端旧兼容入口清理 — 已完成

- 删除 `catalog/fetch.py` 聚合门面和 `lovktv.catalog` 包级旧导出，调用方改用 `audio`、`search`、`lyrics`、`importer` 职责模块。
- 将歌词编排实现归位到 `pipeline/orchestrator.py`，移除 `pipeline/align.py` 旧别名入口。
- 删除 `main` 的动态路由再导出、`runtime` 对 `main` 的反向兼容 helper，以及 `store` 的房间函数兼容导出；公网 API 路径与房间 WebSocket 消息格式不变。
- 房间与时间轴契约归档到 `lovktv/domain/`，根级契约入口同步移除；`domain` 保持纯协议定义，不反向依赖路由或存储。

证据：`cbd2eea` 完成 backend package boundary migration，`2234324` 收紧 domain contract imports；`backend/tests/test_catalog_split.py`、`test_align_modules.py`、`test_room_service.py` 和路由 smoke 覆盖旧入口移除后的调用边界。前端兼容层和旧 Android bridge 也已在 `0ff3f2d` 前合并清理。

## 当前跟进

当前基线为本批提交（2026-08-30）：在 R6 lifespan/部署验收的基础上，R7 backend compatibility cleanup、backend package boundary migration、frontend asset taxonomy 以及 R5B/R5C/R5D 的可运行实现均已合并。R5 仍保持进行中，仅剩 R5D 的真实 APK 与公网产物对比验收：

- R5A：平台能力与页面 DOM contract（已完成 Phone ports、桥隔离、LAN HTTP 回调、降级测试和入口 mount 边界）。
- R5B：TV 播放运行时收敛（删除 classic/QR 旧入口，统一 module 播放路径，补齐播放转场护栏）。
- R5C：shared 资源与类型边界（已完成；timeline、stage FX、bridge/API 类型均纳入检查）。
- R5D：Web/embedded 构建与 manifest/revision（构建链已完成，真实 APK hash/revision 对比待补）。

本次验证：`PYTHONPATH=backend python -m pytest -q backend/tests`（337 passed）；`npm ci --ignore-scripts` 后 `npm run check`（tsc、lint、format）通过。生产验收仍运行 `PYTHONPATH=backend python scripts/accept-production.py --base https://ktv.lovbrowser.com`；资源 parity 工具已由 `backend/tests/test_frontend_parity.py` 覆盖。

> 明确留项（下一批）：在发布机取得真实 TV APK 与同 revision 公网产物后，运行 `python scripts/check-frontend-parity.py --manifest frontend/frontend-dist/manifest.json --apk <tv.apk> --web https://ktv.lovbrowser.com` 完成最终三端一致性验收。本批已闭环 parity 检查工具、adapter、桥隔离、LAN 回调、降级、DOM contract、`mount(root, deps)` 入口、Phone/TV 状态 ownership、R5B 播放运行时、R5C 类型/资源边界和 R5D 构建链。
