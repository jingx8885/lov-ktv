# lov-ktv Android TV

安装后 App 会拉起本机局域网服务：电视 WebView 打开 `http://127.0.0.1:8787/tv.html`，手机扫电视二维码进 `http://电视局域网IP:8787/m.html`。搜歌、下载、人声分离、歌词对齐仍转到「处理服务器」。处理完成后，伴奏 / 导唱 / 歌词 / MTV 会缓存到电视；处理端掉线时仍可点已缓存的歌。

## 导入

用 Android Studio 打开本目录 `android-tv/`，同步 Gradle 后 Run 到 Android TV 模拟器或盒子。构建时会把 `frontend/public` 打进 APK。

命令行（SDK / Gradle / 产物都在外接硬盘）：

```bash
source "/Volumes/外接硬盘/开发数据/android/env.sh"
cd android-tv
gradle --init-script "/Volumes/外接硬盘/开发数据/android/relocate-build.gradle" test assembleDebug
```

或：`/Volumes/外接硬盘/开发数据/android/build-lovktv.sh`

APK：`/Volumes/外接硬盘/开发数据/android/apks/lov-ktv-tv-debug.apk`

## 用法

1. 电脑或 NAS 先跑处理端：`PYTHONPATH=backend .venv/bin/uvicorn lovktv.main:app --host 0.0.0.0 --port 8787`
2. 电视首次填处理服务器，例如 `http://电脑局域网IP:8787`
3. 电视出码后，手机扫码打开点歌页
4. 菜单键可改处理服务器地址
5. 已唱过的歌会留在电视 `filesDir/media/`，断网后曲库只显示这些成品

`AndroidManifest` 声明 `leanback`，触摸屏 optional，允许局域网 HTTP。前台服务类型为 `dataSync`。

低延时麦：`HostService` 在 UDP `18787` 收 `LKTM` 包（48 kHz / mono / s16le），用 `AudioTrack` 外放。`/api/host` 会带 `mic_port`、`mic_sample_rate`。手机请装 `android-phone/`，不要指望浏览器 `tv.html` 收 UDP。
