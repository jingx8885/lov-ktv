# I13 · Android TV APK

Epic: E06  
depends_on: I12

## 合同

Leanback 应用启动后拉起本机局域网服务，WebView 加载 `http://127.0.0.1:8787/tv.html`，支持 DPAD。  
首次填写**处理服务器**地址（默认 `http://lov-ktv.local:8787`）。电视出局域网二维码，手机扫码打开 `/m.html`；搜歌 / 分离 / 对齐走处理服务器。

## 验收

- `AndroidManifest` 含 `leanback` / `touchscreen optional`，以及前台 `HostService`。
- 首次启动能填处理服务器 URL。
- `/api/host` 返回电视局域网 `origin`，电视页用它生成手机码。
- 处理完成的 `karaoke.m4a` / `guide.m4a` / `lyrics.json` / `mtv.mp4` 缓存到电视；处理端不可达时用缓存曲库和本地房间继续唱。
