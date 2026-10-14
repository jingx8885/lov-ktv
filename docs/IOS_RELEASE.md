# iOS 第一版发布指南

## 本版范围与审核取舍

本工程位于 `ios/`，Bundle ID 为 `com.lovktv.phone`，最低 iOS 16，仅面向 iPhone。Capacitor 8.5.3 + Swift 原生桥 + 本地 ES modules；启动页、设置、曲库和遥控 UI 全部打包，不加载远程 m.html。Android 和普通网页继续使用原有 m.html；`phone/platform.js` 增加 Capacitor iOS 判断，并禁止 iOS APK 更新能力。专用 iOS 页面不依赖安卓桥。

连接设置提供两种方式：

- **自己的服务器**：填写服务器根地址和房间码，或扫描电视二维码后确认；原有局域网/HTTPS 连接逻辑不变。
- **官方服务**：固定连接 `https://ktv.lovbrowser.com`，输入已有 API key 和电视房间码。完整 key 只保存在 iOS Keychain（AfterFirstUnlockThisDeviceOnly，不同步或备份到其他设备），Web storage 仅存方式、地址和房间码。留空可使用已有 key；断开并清除会删除 Keychain 条目。填写官方域名也强制走官方模式。原生请求使用 Bearer key，不放 URL，不接受重定向。

支持搜索分页、点歌、队列、暂停/继续、切歌、音量、原生扫码、手机原曲试听及后台音频。自托管试听取 `/media/{id}/original.mp3`，官方试听取鉴权后的 `/api/remote/ios/media/{id}`，最大 30 MB；下载完成后播放，不支持 OSS 重定向。没有 UDP 麦克风或录音功能。

官方接口统一位于 `/api/remote/ios`，每次校验 key 哈希及对应账号的套餐、状态和到期时间。此命名空间无论是否发送 `X-LovKTV-Platform: ios` 都执行相同限制：只允许 `audio_source=upload` 且无网易 ID 的本地上传内容；未知、历史空来源及所有公共提供商均排除。曲库总数/分页、队列、当前播放、点歌、举报和试听使用同一限制，仅返回必要文本字段。新上传记录写入 upload 来源；不自动将历史未知记录视为授权内容。审核员演示内容须由运营者确认权利后上传。客户端不展示公共提供商或调用聚合搜索/导入接口。普通网页、Android 和电视原接口不变。

会员沿用现有 Stripe 权益；网页 `/billing.html` 提供 API key 申请、摘要查看、重新生成和吊销。每个账号保留一个有效 key，数据库仅存 SHA-256 哈希及短前缀，完整值仅生成时显示一次。非会员不能申请；到期后仍可查看摘要或吊销，重新生成立即使旧 key 失效。key 不能用于账户或支付接口。API key 无效、吊销或会员失效时，App 统一显示“API key 无效或已失效”。

App 只允许输入已有 key，不包含购买、开通会员、价格、支付或申请 key 的链接/引导；专用打包页面不加载 billing 页面。账号创建和会员管理均在 App 外完成。自托管仍不要求账号。正式提交应如实向 Apple 说明官方功能的外部会员关系，由 Apple 判断 3.1.1/3.1.3 适用性，不能以移除链接等同于保证审核通过。自托管请关闭 `LOVKTV_POINTS`。

内容安全：歌曲可举报并在本机屏蔽。举报存入用户服务器的 `remote_reports`；不展示用户身份、聊天或社区。审核环境必须部署本次后端，管理员必须实际处理举报，不能只部署客户端。

## 1. 环境与依赖

这台 Mac 当前 `xcode-select -p` 指向 `/Library/Developer/CommandLineTools`，未安装完整 Xcode。先安装支持当前 App Store 提交 SDK 要求的最新版 Xcode（Capacitor 8 要求 Xcode 26 或更高），首次启动接受许可、安装 iOS SDK 和模拟器，再执行：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -version
node --version  # Node 22 或更高
cd ios
npm ci
npm run build
npx cap sync ios
npx cap open ios
```

也可直接 `open ios/App/App.xcodeproj`（从仓库的 ios/ 目录运行）。本工程用 Swift Package Manager，不需要 CocoaPods。等待 Xcode 下载 Capacitor Swift 包。不要设置 `server.url` 或 `allowNavigation`，也不要把整个 frontend/public 复制进 App；build 脚本只打包专用网页、Capacitor runtime 与品牌图标。每次修改网页后重新 build + sync。

## 2. 签名、版本与真机

在 Xcode 选择 App target → Signing & Capabilities：启用 Automatically manage signing，选择自己的付费 Apple Developer Team，确认 Bundle Identifier `com.lovktv.phone`。Apple Developer 网站对应 App ID 必须属于该团队。

General → Version 当前为 `1.0`、Build 为 `1`。iOS 版本须使用 Apple 接受的最多三段数字格式；仓库 Android VERSION 是四段，不可直接填入 CFBundleShortVersionString。以后每次上传递增 Build。此次只是开发提交，不创建发版 tag、不发布 Android APK。

连接 iPhone，信任 Mac，启用 Developer Mode；选择该设备并运行。模拟器无法代替相机和后台播放真机检查。扫码使用 VisionKit DataScanner，老设备不支持时仍可手填地址。

权限：Info.plist 配置相机文案、局域网文案、`NSAllowsLocalNetworking` 和 `UIBackgroundModes=audio`。没有麦克风权限。HTTP 仅限 RFC1918 IPv4 或 `.local`，其他地址必须 HTTPS，不允许全局 ATS 放行。若特定系统版本拒绝数字 IP 的 HTTP，请给服务器配置 `.local` 名称或有效 HTTPS，并在目标系统实测；不要添加 NSAllowsArbitraryLoads 绕过。

真机提交前逐项验收：

- 首次启动无联网；默认选择自己的服务器，官方服务仅在用户连接后访问；错误地址、无效码、断网、服务器错误可恢复；扫描只填写，确认后才访问。
- HTTPS 与局域网 HTTP、拒绝/允许相机与局域网权限、重启后地址保存、切换服务器不串数据。
- 配一间实际运行的电视房间，测试搜索/分页/点歌/队列/暂停/切歌/音量，手机锁屏不影响电视。
- 本地 original.mp3 试听、停止、锁屏播放/暂停、耳机拔出、来电中断、回到前台；OSS 重定向应明确报错。试听不是实时电视监听。
- 举报到达管理员队列、屏蔽在重启后仍有效、清除屏蔽、清除本机数据、切服和停止时取消未完成试听。
- iPhone SE 与大屏、横竖屏、深浅色、最大文字、VoiceOver 全流程；当前 Web UI 采用安全区、44px 触控和语义标签，仍需真机确认 Dynamic Type 行为。
- App 内找不到任何公共音源、购买/开通会员/价格/外部购买引导、申请 key 外链、广告、注册或 APK 下载入口；自托管无需账号，官方仅输入已有 key。
- 官方 key 保存后重启、留空重连、替换、吊销、会员到期、错误 key、断开清除；切至自托管请求不携带 key。官方混合曲库中的公共来源不能出现在搜索、队列或试听。

设计静态检查暂评 6/10：安全区、触控、深浅色和语义结构已实现；10/10 尚需真机 Dynamic Type、VoiceOver、原生导航体验及全部屏幕布局验收，不能以静态检查替代。

## 3. 管理员处理举报

后端启动会创建 SQLite/Postgres 表，手工管理 Supabase 时同步执行 `docs/schema.postgres.sql` 新增表。举报不需要账号，但限制字段长度、验证歌曲存在，队列上限 10000。建议自托管反代再设置请求速率限制。

使用已有管理员认证（`LOVKTV_ADMIN_TOKEN` 或现有后台登录 Cookie）：

- `GET /api/admin/remote-reports`：按时间返回最早 200 条。
- 调查后，用现有后台歌曲管理删除违规歌曲；对于反复违规的上传者，由服务器管理员撤销其服务器访问权限。本 App 不显示或提供关注用户功能。
- `DELETE /api/admin/remote-reports/{id}`：处理完清除举报，不会自动删除歌曲。

定期轮询和人工处理，建议 24 小时内响应。公开隐私/支持页写明真实联系邮箱、举报处理期限和服务器运营者责任；不要留下占位联系信息。自托管的曲库不等于自动拥有版权，审核演示只能用自有/授权内容。

## 4. App Store Connect 记录与地区

登录 App Store Connect → My Apps → + → New App：iOS，名称 LovKTV Remote（以可用名称为准），主语言与商店描述一致，Bundle ID 选择 `com.lovktv.phone`，SKU 自定如 `lovktv-ios-phone`。填写分类（音乐）、年龄分级、内容权利、支持 URL、隐私政策 URL。按真实能力回答 UGC、网络访问等问卷，不可因为自托管而全部填“无”。

Pricing and Availability → 明确取消“中国大陆”，不要选择未来新增地区自动上架而遗漏地区审核。其他目标地区由主人选择。填写开发者联系方式；欧盟地区销售时按实际主体完成 DSA trader 信息。

本地界面为中文；面向非中文用户上线前需翻译 UI 和对应商店材料。本版可以先选中文用户所在的非中国大陆地区。

## 5. 隐私标签与隐私清单

App 无广告/分析 SDK、无跟踪、无联系人/位置/麦克风采集。官方服务通过 API key 关联已有账号。相机识别在本机完成，图像不上传。地址、房间码、屏蔽清单在本机 Web storage；清除按钮删除这些数据，服务器举报不会被本机清除删除。

请求会把搜索词、房间操作、举报原因发送给用户指定服务器；服务器自然能看到连接 IP。选择官方服务时，开发者运营的服务器接收请求，key 可关联账号。App Store 隐私表必须按实际发布架构填写：若仅直接连接用户自行控制的第三方服务器，判断是否符合 Apple 的收集定义；若开发者运营审核以外的服务器并保存这些数据，按实际勾选搜索历史、其他用户内容（举报）等用途“App 功能”，说明是否关联身份与保存期限，不能照抄“完全不收集”。

`PrivacyInfo.xcprivacy` 声明不跟踪；文件元数据访问用于本机下载音频大小检查，原因 C617.1。Capacitor 自带 SDK 清单也会打包。Archive 后在 Organizer 生成 Privacy Report，核对最终二进制及第三方依赖，必要时修正标签和清单。隐私清单不能代替公开隐私政策。

## 6. 截图与上传

先准备真实运行截图，至少展示连接设置、已配置服务器曲库、房间遥控、举报与屏蔽。不得显示公共音源或付费页面。App Store Connect 当前支持的 iPhone 6.9 英寸组可使用 1320×2868（竖）/2868×1320（横）；也常接受 1290×2796、1260×2736，以当次上传页最新要求为准。若平台要求 6.5 英寸备用组，可用 1242×2688 或 1284×2778。每种本地化最多 10 张，不要拉伸。当前 target 仅 iPhone；若以后启用 iPad，另提供 13 英寸组截图（如 2064×2752）。图标由 `frontend/public/brand/icon.png` 生成 1024×1024 不透明 PNG。

Xcode 选 Any iOS Device (arm64) → Product → Archive。完成后 Organizer → Validate App → Distribute App → App Store Connect → Upload。处理完成后在 App Store Connect 的版本页面选 build，完成出口合规问卷（按实际 TLS/加密使用回答）、内容版权、隐私标签、年龄评级、截图、审核联系信息，先 TestFlight 测试，再 Add for Review / Submit。不要把“成功 Archive”当成审核通过。

## 7. 审核备注模板（填写所有占位内容）

```text
LovKTV Remote offers two connection modes: a user's own self-hosted server,
and our official service at https://ktv.lovbrowser.com using an existing API key.
Official keys belong to active members whose membership is managed outside
this app through our existing Stripe system. The app only accepts an existing
key: it contains no purchase, subscription signup, price, external purchase
instructions, or links for obtaining a key. Self-hosted use requires no account.
The interface is bundled. No public music providers, scraping, catalog import,
registration, ads or payment UI are included. Official iOS APIs expose only
locally uploaded content and filter public/unknown sources from search, queue,
current playback and audio preview. We do not distribute in mainland China.

Official review API key: [supply a dedicated test key privately in App Review]
Official room code: [code; keep TV host online throughout review]
Official steps: Settings → Official service → enter existing test API key and
room code → Connect → Library → search [owned recording title] → Queue.
Self-hosted setup is an alternative:
Review server: https://[dedicated-review-server]
Room code: [code]
No account or password is required. Keep this room and its TV host online
throughout review. The demo library contains only recordings we own or are
licensed to use. [Explain rights and attach evidence if needed.]

Steps: Settings → enter server and room → Connect → Library → search [title]
→ Queue → Remote → pause/resume/skip/volume. To test background audio, tap
Phone Preview on [locally hosted original.mp3 song], then lock the phone.
Playback continues through the native audio player. Camera permission is only
used for scanning a TV QR code; manual setup is always available.

Content can be reported and blocked from each song row. Reports reach the
configured server administrator. Moderation contact: [real email and response SLA].
Privacy policy: [public HTTPS URL]. Support: [public HTTPS URL].
```

测试 key 准备：在 App 外为专用审核账号配置真实有效且覆盖整个审核周期的会员权益，在网页 `/billing.html` 生成专用 key，完整值仅显示一次。将测试 key 私下填入 App Store Connect 审核备注，不写入仓库、截图、文档或日志。准备官方房间和明确授权上传音频并保持在线；提交前实测 key、到期时间、搜索/点歌/试听，审核期间避免轮换或吊销，结束后吊销。不要要求审核员购买会员或自行申请 key。

审核服务器必须在公网稳定可用，提供可实际操控的房间、可本地试听的授权原曲；不能让审核员先自行部署，也不能把演示服务硬编码进 App。可以附短演示视频帮助说明手机操作与电视输出关系。4.2 最低功能审核由 Apple 决定，本地打包、原生扫码和音频不能保证免拒。

## 8. 本机验证与尚未验证

已执行：npm 安装与 cap sync、iOS 连接/安全存储桥调用/打包边界 Node 测试 6 项、相关后端测试 39 项（含 key 生命周期、会员到期、音源边界）、前端 Node 测试 21 项、ESLint、Swift 语法解析、plist/project 文件校验。运行依赖 `npm audit --omit=dev` 为 0；开发工具链仍报告 uuid → xcode → Capacitor CLI 的 3 项 moderate，未强行改其跨主版本依赖。

全仓 `npm run check` 当前被已有 `public/login/js/login.js:107` 的 LovKtvNativeBridge.version 类型缺失挡住；单独 format:check 报 9 个既有文件格式问题，未批量改无关文件。本次修改文件格式检查通过。

由于只有 Command Line Tools，未完成 iOS SDK 类型检查/链接、模拟器截图、真机扫码/局域网/后台音频、签名、Archive、TestFlight 或商店上传；这些都是提交审核前必做，不能称为已经具备可上传的已验收 IPA。

复跑：

```bash
cd ios
npm run sync
npm test
cd ..
LOVKTV_DATA=/private/tmp/lovktv-ios-tests .venv/bin/python -m pytest backend/tests/test_remote_keys.py backend/tests/test_remote_reports.py backend/tests/test_schema.py backend/tests/test_billing.py backend/tests/test_phone_platform.py backend/tests/test_platform_boundary.py backend/tests/test_room.py backend/tests/test_room_service.py -q
node --experimental-vm-modules --test frontend/tests/*.test.mjs
npm run lint --prefix frontend
```
