# I13 · Android TV APK

Epic: E06  
depends_on: I12

## 合同

Leanback 应用，WebView 加载 `{server}/tv`，支持 DPAD。  
可配置服务器地址（默认 `http://lov-ktv.local:8787` 与局域网探测页）。

## 验收

- `AndroidManifest` 含 `leanback` / `touchscreen optional`。
- 首次启动能填服务器 URL。
