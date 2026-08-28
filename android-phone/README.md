# lov-ktv Android 点歌台

手机原生点歌 + 低延时数字麦。点歌走现有 HTTP；麦用 `AudioRecord` 采 48 kHz / mono / s16le，约 10 ms 一包 UDP 发到电视。网页电视收不了 UDP，低延时麦必须装 `android-tv/`。

## 导入

用 Android Studio 打开本目录 `android-phone/`，同步 Gradle 后 Run 到手机。

命令行（SDK / Gradle / 产物都在外接硬盘）：

```bash
source "/Volumes/外接硬盘/开发数据/android/env.sh"
cd android-phone
gradle --init-script "/Volumes/外接硬盘/开发数据/android/relocate-build.gradle" test assembleDebug
```

或：`/Volumes/外接硬盘/开发数据/android/build-lovktv.sh`

APK：`/Volumes/外接硬盘/开发数据/android/apks/lov-ktv-phone-debug.apk`

## 用法

1. 电视先装并打开 `android-tv/`，墙上会出现房间码和二维码
2. 手机点「扫码进房」，对准电视二维码；也可以手填房间码和服务器地址
3. 只点歌：服务器填 `https://ktv.lovbrowser.com`（或处理端）
4. 要低延时麦：服务器填电视局域网地址，点「开麦」
5. 点歌台可搜歌入库、点歌、顶歌、切歌、切换原唱/伴唱、调音量
6. 公网处理端的 `/api/host` 里 `mic_port` 为 0，开麦按钮会提示需要电视 App

手机不要外放伴奏。电视出声时手机离音箱远一点，这条路径没有网页那种回音消除。
