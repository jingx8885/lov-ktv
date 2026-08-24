# lov-ktv Android TV

Leanback 壳：首次填服务器地址，WebView 打开 `{server}/tv.html`。遥控器方向键点按钮，菜单键改服务器。

## 导入

用 Android Studio 打开本目录 `android-tv/`，同步 Gradle 后 Run 到 Android TV 模拟器或盒子。

命令行（已装 Android SDK / Gradle）：

```bash
cd android-tv
gradle wrapper --gradle-version 8.2
./gradlew assembleDebug
```

APK：`app/build/outputs/apk/debug/app-debug.apk`

## 用法

1. 电脑先跑 lov-ktv：`http://0.0.0.0:8787`
2. 电视填 `http://电脑局域网IP:8787`（默认识别 `http://lov-ktv.local:8787`）
3. 电视扫码登录：手机微信或本机身份确认
4. 同一页继续搜歌点唱、扫色歌词

`AndroidManifest` 声明 `leanback`，触摸屏 optional，允许局域网 HTTP。
