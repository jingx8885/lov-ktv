# LovKTV iPhone 原生遥控端

SwiftUI + Swift 6（iOS 17+），与 `ios/`（Capacitor 壳）共存。
功能对齐 m.html 手机端：点歌台同屏完成点歌全流程（正在唱卡 + 暂停/切歌 +
伴奏/音量/麦克风 + 歌词字号），分段面板 = 已点/曲库/在线/歌词/歌单；
搜歌页在线搜试听入库；听歌页歌词高亮跟唱；学习页单词本/抽认卡。
房间操作：待唱队列（唱这首/置顶）、人声开关、麦克风增益、歌词模式与字号、
显示模式、手机试听、收藏、屏蔽/举报、扫码连服务器、官方服务 API key（Keychain）、
WebSocket 快照实时推送（/ws/rooms/{code}）+ 3s 轮询兜底。

UI 基元集中在 `LovKTV/Views/AppStyle.swift`：KTV 调色板、GlassCard、
SegBar（分段）、ChipButton（胶囊动作）、NowActButton（点歌台/听歌页共用播控）、
IconCircleButton（行内图标钮）、SearchField、DeskEmpty。新增页面先复用这套，
不要再造第二套按钮画法。

白名单与连接校验与旧 Capacitor RemotePlugin 同源；bump/play 仅自建服可用
（官方 ios_router 不暴露，按钮在官方服会返回 404 提示，属预期）。

## 构建

```bash
cd ios-native
xcodegen                       # 生成 LovKTV.xcodeproj（不入 git，重新生成即可）
xcodebuild -scheme LovKTV \
  -destination 'platform=iOS Simulator,name=iPhone 17' build
# 或用 axiom 的 axbuild（日志落盘 + 短摘要）
~/.codex/axiom/tools/axbuild xcodebuild -scheme LovKTV \
  -destination 'platform=iOS Simulator,name=iPhone 17' build
```

单元测试：`xcodebuild -scheme LovKTV -destination '...' test`（`LovKTVTests` 覆盖
ConnectionValidator / RemotePath / APIWhitelist / 解码）。

真机调试：自动签名 + 免费证书可跑 7 天；首次需在系统设置里信任开发者证书。
局域网 HTTP 地址只允许 10.x/172.16-31.x/192.168.x 和 *.local，公网必须 HTTPS，
与 `ios/web/policy.js` 同规则。
