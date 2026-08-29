# 前端耦合分析与重构方案

更新时间：2026-08-30（基于 `0ff3f2d`）

## 结论

当前前端的主要风险不是文件数量，而是四个隐式接口同时承担了页面、平台和发布边界：

1. DOM `id/class` 是没有类型和版本的页面 API。
2. `window.LovKtv*` 是没有版本和统一适配层的 WebView ABI。
3. `phone/state.js`、`tv/state.js` 和 `api.js` 是跨模块共享的可变对象。
4. Android TV 与公网 Web 已改为消费 `frontend-dist/manifest.json` 的同一构建链；真实 APK 解包与公网 bundle 的 hash/revision 对比仍未自动化。

因此一次看似局部的修改，可能影响浏览器 TV、TV APK 局域网点歌页、浏览器 Phone、Phone APK 四种形态。

## 运行拓扑

```text
公网浏览器
├── /tv.html -> TV 页面 -> /api /media /ws
└── /m.html  -> Phone 页面 -> /api /media /ws

Android TV APK
├── 构建时复制整个 frontend/public
├── HostServer 在 127.0.0.1/LAN 提供静态页，并代理处理端 API
├── WebView 打开本地 tv.html
└── JS <-> Kotlin: LovKtvNative

Android Phone APK
├── 不打包前端，WebView 远程加载 m.html
├── Java 注入 fetch，把私有 LAN HTTP 转给原生
└── JS <-> Kotlin: LovKtvPhone
```

TV APK 提供给手机的 `m.html` 仍是 APK 内嵌快照；构建链已统一，但已安装 APK 在未升级前仍可能与公网手机运行不同版本的 Phone 前端。

## 当前耦合清单

### P0：启动和运行时协议

- `phone/app.js` 在入口阶段直接读取固定 DOM 节点；核心节点缺失会让整个页面启动失败。
- TV 播放统一由 `tv/app.js` module 运行时接管；旧 `boot-play.js` / `boot-qr.js` 入口已删除，避免重复 timer、房间初始化和 `LovKtvRemote`。
- Android Phone 通过注入脚本覆盖全局 `fetch`，同时维护 `LovKtvOnHttp`、`LovKtvOnLanHttp`、`__lovktvLanFetch` 等隐式回调协议。
- Android TV 的 Kotlin bridge 已集中到 `tv/platform.js` adapter；业务侧仍通过 `window.LovKtvRemote.*` 能力工作，未知能力按 no-op/fallback 降级。

### P1：状态和模块边界

- `phone/state.js` 仍同时容纳房间、曲库、播放器、歌词编辑、学习模式、RTC、网页麦和原生麦状态；ownership 拆分是留项。
- `tv/state.js` 仍同时容纳房间同步、播放恢复、歌词、MTV、音频、特效、登录和麦状态；ownership 拆分是留项。
- `phone/install.js` 通过 `installApi()` 注入一个可变 service locator；各模块既读 `state` 又调用 `api` 中的其他模块。
- TV 播放运行时按 `runtime`、`media`、`lyric`、`remote`、`room` 归档；`audio/*` 只依赖 `runtime/tick.js`，不再引用同级散落入口。
- Phone 播放运行时统一位于 `phone/player/js/playback`，房间运行时位于 `phone/room/js/room`；`room/state.js` 负责 snapshot/stamp，播放模块不再与房间目录同级混排。

### P1：跨目录泄漏

- 舞台特效已归入 `shared/fx/js/stage`，Phone 学习和 TV 播放共同消费共享实现；Phone 不再加载或引用 `tv/` 目录。
- `timeline.js` 和共享舞台特效脚本均位于稳定职责目录，并纳入 TypeScript 检查边界。
- `tv/stage/css/stage.css` 包含 `body.phone` 选择器，说明样式边界发生过反向渗透。

### P1：发布和协议漂移

- Android TV Gradle 现由 `copyWebAssets` 调用 `scripts/build-frontend-dist.py`，将带 manifest 的产物复制进 APK；后端在存在 dist 时优先服务同一目录。
- 后端与 TV 均从 manifest 读取内容 SHA-256 截断 revision，并保留 git commit；但尚无真实 APK 解包后的文件清单/哈希与公网文件的自动对比。
- backend domain contracts、前端 `models.d.ts`/bridge 声明和 Android DTO 仍是多份模型；本批只完成边界与类型检查，生成式客户端仍是后续工作。
- 当前依赖安装后 `npm run check`（tsc、ESLint、Prettier）可作为门禁；历史上的 bridge、`Song.song_id`、学习状态漂移错误已清理。

## 当前证据与后续计划

当前基线为 `0ff3f2d`。已合并并可追溯的改动包括：R7 backend compatibility cleanup 与
package boundary migration（`cbd2eea`、`2234324`）、Phone/TV 资源 taxonomy（`cabb1c4`）、
TV module 播放运行时（`1d3374b`）以及 Web/embedded manifest 构建链。

验证命令与结果：

- `PYTHONPATH=backend python -m pytest -q backend/tests` — 335 passed。
- `cd frontend; npm ci --ignore-scripts; npm run check` — tsc、ESLint、Prettier 全部通过。
- `backend/tests/test_assets.py`、`test_frontend_split.py`、`test_frontend_types.py`、
  `test_tv_playback.py` 提供资源路径、manifest revision、类型边界和 TV 播放 smoke 覆盖。

下一批聚焦三个明确留项：逐模块改成 `mount(root, deps)`；将 Phone/TV 大状态迁移到有
ownership 的 room/catalog/player（TV 为 room/playback/audio/platform）store；构建真实 TV
APK 后解包，与公网 `frontend-dist` 逐文件比较路径、hash 和 manifest revision。未完成这些
对比前，不宣称 APK 与公网资产已完全一致。

## 目标边界

```text
frontend/core
├── contracts        房间、歌曲、歌词运行时校验
├── stores           room / catalog / tv-playback / phone-player
└── platform         Http / Media / Mic / Scanner / Remote 接口

frontend/shared      纯工具：DOM、歌词绘制、音频算法、i18n

frontend/tv-web      TV 浏览器/TV WebView 的 DOM shell
frontend/phone-web   Phone 浏览器/Phone WebView 的 DOM shell

platform/android-tv     LovKtvNative adapter + HostServer 适配
platform/android-phone  LovKtvPhone adapter + LAN fetch 适配
```

目标是让业务模块只依赖 `core` 接口，不直接访问 `window.LovKtv*`、全局 DOM 或另一个 feature 目录。

## 改造顺序

### 1. 先冻结平台适配层

- 定义 `Platform`、`HttpPort`、`MicPort`、`MediaPort`、`RemotePort`、`ScannerPort`。
- 浏览器、Android Phone、Android TV 各有一个 adapter。
- 原生桥名称、回调、超时和能力查询只出现在 adapter 中，业务层不再直接读写 `window.LovKtv*`。
- 给桥协议增加 `version` 和 `capabilities`，未知能力必须可降级。

### 2. 拆状态 ownership

- 保留现有 `phone/player/js/playback/state.js`、`phone/room/js/room/state.js` 和 `tv/playback/js/runtime/state.js` 的纯逻辑方向。
- [ ] 把 `phone/state.js` 拆成 room/catalog/player/platform 四个 store。
- [ ] 把 `tv/state.js` 拆成 room/playback/audio/platform 四个 store。
- 每个 store 只暴露 snapshot、command 和事件，不允许任意模块写入别的领域状态。
- `guardState()` 只能作为临时保护，最终要补运行时状态迁移校验。

### 3. 建立 DOM contract

- [ ] 页面功能改成 `mount(root, deps)`，模块只查询自己的 root（当前仍有入口直接查询全局 DOM）。
- 为 `m.html`、`tv.html` 建立必需节点清单和 smoke test。
- `$must()` 不再作为跨页面的全局入口；缺少可选节点时模块应局部降级。
- Android Phone 的扫码按钮注入改为稳定的 data attribute 或专用 mount point，不再依赖 `.sheet`、`.lang-picker` 等视觉选择器。

### 4. 收敛 TV 播放路径

- 已删除 `boot-play.js` 的 8 秒 classic fallback 及 `boot-qr.js` 重复房间初始化；TV 浏览器与 TV APK 共用 `tv/app.js`。
- `LovKtvRemote` 只由一个 controller 注册。
- 播放、歌词、MTV、恢复、预取分别成为 controller 的子模块，通过事件协作。
- 为浏览器 TV 和 TV APK 使用同一组播放协议 smoke test。

### 5. 收回 shared 和类型检查边界

- 舞台特效脚本已按顺序归档到 `shared/fx/js/stage`，播放器 timeline 位于 `phone/player/js/playback`，均纳入可检查路径。
- Phone 学习特效不再从 `tv/` 目录加载。
- [x] shared 模块不得引用 phone/tv 或原生全局。
- [x] 将原生桥、`LovI18n`、内部事件和 API 返回模型补进类型层；`npm run check` 错误已清空。

### 6. 统一协议和发布产物

- 以后端 contracts/OpenAPI 为 API 模型单一来源，生成前端类型和 Android DTO，或至少在 CI 比对三端字段。
- [x] 一次构建生成 `frontend-dist` 和 `manifest.json`，后端静态服务和 TV APK 都消费同一份产物。
- [x] asset revision 使用 git commit/content hash，不再使用 APK 安装时间。
- [ ] 增加真实公网静态文件与 TV APK 内嵌静态文件的路径、hash、入口 smoke test（源码/manifest 契约已覆盖，APK 对比未完成）。

## 验收矩阵

每个涉及前端边界的变更至少验证：

| 形态 | 页面 | 平台能力 | 必测内容 |
|---|---|---|---|
| Web TV | `/tv.html` | 浏览器音频/RTC | 开房、播放、歌词、切歌、原伴唱 |
| TV APK | 本地 `tv.html` | `LovKtvNative`、缓存、遥控器 | 冷启动、断处理端、MTV、遥控键 |
| Web Phone | `/m.html` | 浏览器 fetch/麦 | 搜歌、入库、排队、歌词播放器 |
| Phone APK | 远程/LAN `m.html` | `LovKtvPhone`、扫码、LAN HTTP、原生麦 | 扫码绑定、LAN 回退、开麦、重连 |

协议测试还应覆盖：无原生桥、桥能力缺失、LAN 不可达、处理端不可达、旧版 TV APK 提供旧页面。

## 不在本轮做的事

- 不改变公网 API 路径、房间 WebSocket 消息格式和媒体目录。
- 不把 Web、TV、Phone 立即改成三套独立 UI；先拆协议和平台边界，再决定哪些视觉组件真正复用。
- 不在没有 smoke test 的情况下直接引入大规模 bundler 重写。
