# LovKTV iPhone 原生遥控端

SwiftUI + Swift 6（iOS 17+），与 `ios/`（Capacitor 壳）共存，功能对齐网页遥控端：
搜索点歌、播放/切歌/音量、待唱队列、手机试听、屏蔽/举报、扫码连服务器、官方服务 API key（Keychain）。

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
