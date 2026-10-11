# iOS 第一版发布指南

## 本版范围与审核取舍

本工程位于 `ios/`，Bundle ID 为 `com.lovktv.phone`，最低 iOS 16，仅面向 iPhone。Capacitor 8.5.3 + Swift 原生桥 + 本地 ES modules；启动页、设置、曲库和遥控 UI 全部打包，不加载远程 m.html。Android 和普通网页继续使用原有 m.html；`phone/platform.js` 增加 Capacitor iOS 判断，并禁止 iOS APK 更新能力。专用 iOS 页面不依赖安卓桥。

用户手动填写自己的服务器根地址和房间码，或扫描现有电视 `/m.html?room=...` 二维码，核对后连接。没有默认服务器、公共音源列表、聚合搜索、抓取歌词、上传或处理入口。搜索仅调用指定服务器的 `/api/songs` 已入库曲库；第一版的“可配置音源”就是这个服务器曲库，不支持额外公共搜索插件。服务器重定向被拒绝，WebView 外部导航被拒绝，后端返回的文本使用 textContent 显示。

支持搜索分页、点歌、队列、暂停/继续、切歌、音量、原生扫码、手机原曲试听及后台音频。试听取指定服务器 `/media/{id}/original.mp3`，最大 30 MB，下载完成后播放；不支持 OSS 重定向，管理员须保留本地音频。本机屏蔽不会删除电视队列，也不会阻止其他遥控器播放。没有 UDP 麦克风，也没有任何录音功能。

本版**不提供注册或任何登录**，不展示 Google、微信、LovBrowser，因此不引入 Sign in with Apple；不在 App 内创建账号，账号删除接口不在本版范围。没有 Stripe、外部支付、广告积分、Play Billing、订阅入口或 APK 更新。基础遥控不必付费，故不做 IAP。自托管服务器请关闭 `LOVKTV_POINTS`，否则点歌可能被服务器拒绝；App 只显示联系管理员的错误，不引导购买。

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

- 首次启动无联网、无默认服务；错误地址、无效码、断网、服务器错误可恢复；扫描只填写，确认后才访问。
- HTTPS 与局域网 HTTP、拒绝/允许相机与局域网权限、重启后地址保存、切换服务器不串数据。
- 配一间实际运行的电视房间，测试搜索/分页/点歌/队列/暂停/切歌/音量，手机锁屏不影响电视。
- 本地 original.mp3 试听、停止、锁屏播放/暂停、耳机拔出、来电中断、回到前台；OSS 重定向应明确报错。试听不是实时电视监听。
- 举报到达管理员队列、屏蔽在重启后仍有效、清除屏蔽、清除本机数据、切服和停止时取消未完成试听。
- iPhone SE 与大屏、横竖屏、深浅色、最大文字、VoiceOver 全流程；当前 Web UI 采用安全区、44px 触控和语义标签，仍需真机确认 Dynamic Type 行为。
- App 内找不到任何公共音源、支付、广告、注册、第三方登录、APK 下载入口；无需登录即可完成基本功能。

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

App 无广告/分析 SDK、无跟踪、无账号、无联系人/位置/麦克风采集。相机识别在本机完成，图像不上传。地址、房间码、屏蔽清单在本机 Web storage；清除按钮删除这些数据，服务器举报不会被本机清除删除。

请求会把搜索词、房间操作、举报原因发送给用户指定服务器；服务器自然能看到连接 IP。开发者不设默认接收端。App Store 隐私表必须按实际发布架构填写：若仅直接连接用户自行控制的第三方服务器，判断是否符合 Apple 的收集定义；若开发者运营审核以外的服务器并保存这些数据，按实际勾选搜索历史、其他用户内容（举报）等用途“App 功能”，说明是否关联身份与保存期限，不能照抄“完全不收集”。

`PrivacyInfo.xcprivacy` 声明不跟踪；文件元数据访问用于本机下载音频大小检查，原因 C617.1。Capacitor 自带 SDK 清单也会打包。Archive 后在 Organizer 生成 Privacy Report，核对最终二进制及第三方依赖，必要时修正标签和清单。隐私清单不能代替公开隐私政策。

## 6. 截图与上传

先准备真实运行截图，至少展示连接设置、已配置服务器曲库、房间遥控、举报与屏蔽。不得显示公共音源或付费页面。App Store Connect 当前支持的 iPhone 6.9 英寸组可使用 1320×2868（竖）/2868×1320（横）；也常接受 1290×2796、1260×2736，以当次上传页最新要求为准。若平台要求 6.5 英寸备用组，可用 1242×2688 或 1284×2778。每种本地化最多 10 张，不要拉伸。当前 target 仅 iPhone；若以后启用 iPad，另提供 13 英寸组截图（如 2064×2752）。图标由 `frontend/public/brand/icon.png` 生成 1024×1024 不透明 PNG。

Xcode 选 Any iOS Device (arm64) → Product → Archive。完成后 Organizer → Validate App → Distribute App → App Store Connect → Upload。处理完成后在 App Store Connect 的版本页面选 build，完成出口合规问卷（按实际 TLS/加密使用回答）、内容版权、隐私标签、年龄评级、截图、审核联系信息，先 TestFlight 测试，再 Add for Review / Submit。不要把“成功 Archive”当成审核通过。

## 7. 审核备注模板（填写所有占位内容）

```text
LovKTV Remote is a remote control for a user's own self-hosted lov-ktv server.
The interface is bundled in the app. The app includes no public music providers,
web scraping, public catalog import, account registration/login, ads, purchases,
or links to external payment. Search only queries the configured server's
existing library. We do not distribute this app in mainland China.

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

审核服务器必须在公网稳定可用，提供可实际操控的房间、可本地试听的授权原曲；不能让审核员先自行部署，也不能把演示服务硬编码进 App。可以附短演示视频帮助说明手机操作与电视输出关系。4.2 最低功能审核由 Apple 决定，本地打包、原生扫码和音频不能保证免拒。

## 8. 本机验证与尚未验证

已执行：npm 安装与 cap sync、iOS 接口/打包边界 Node 测试、相关后端测试 29 项、前端 Node 测试 21 项、ESLint、Swift 语法解析、plist/project 文件校验。运行依赖 `npm audit --omit=dev` 为 0；开发工具链仍报告 uuid → xcode → Capacitor CLI 的 3 项 moderate，未强行改其跨主版本依赖。

全仓 `npm run check` 当前被已有 `public/login/js/login.js:107` 的 LovKtvNativeBridge.version 类型缺失挡住；单独 format:check 报 9 个既有文件格式问题，未批量改无关文件。本次修改文件格式检查通过。

由于只有 Command Line Tools，未完成 iOS SDK 类型检查/链接、模拟器截图、真机扫码/局域网/后台音频、签名、Archive、TestFlight 或商店上传；这些都是提交审核前必做，不能称为已经具备可上传的已验收 IPA。

复跑：

```bash
cd ios
npm run sync
npm test
cd ..
LOVKTV_DATA=/private/tmp/lovktv-ios-tests .venv/bin/python -m pytest backend/tests/test_remote_reports.py backend/tests/test_schema.py backend/tests/test_phone_platform.py backend/tests/test_platform_boundary.py backend/tests/test_room.py backend/tests/test_room_service.py -q
node --experimental-vm-modules --test frontend/tests/*.test.mjs
npm run lint --prefix frontend
```
