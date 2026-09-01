# lov-ktv Agent 原则

家庭 / 包厢自托管 KTV。处理端跑搜歌、人声分离、歌词对齐；电视或浏览器唱，手机扫码点歌。

## 上线

- 公网：`https://ktv.lovbrowser.com`
- 机器：`ubuntu@43.134.133.185`，目录 `~/lov-ktv`
- 发版来源：先提交并 `git push origin HEAD`，再在 43 上 `git pull`。仓库默认分支是 `master`；`main` 与 `master` 应对同一发版 commit，不要两边各写各的。
- 不要把应用代码挂进容器。运行中的内容必须来自当前 git commit 打出来的镜像。
- 镜像分两段：`base`（系统包 / Python 依赖 / ONNX）和 `app`（backend + frontend）。日常 `--build` 会复用 `base`，只重烤应用层。
- 上线命令：

```bash
ssh ubuntu@43.134.133.185
cd ~/lov-ktv
git pull --ff-only origin master
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env up -d --build
```

- 只改 `frontend/public`、要立刻看效果时，可先拷进运行中的容器，再按上面 `--build` 让镜像与 git 一致：

```bash
sudo docker cp ~/lov-ktv/frontend/public/. lov-ktv-lov-ktv-1:/app/frontend/public/
```

- 验收必须走公网，不只看本机：
  - `https://ktv.lovbrowser.com/` 落地页
  - `https://ktv.lovbrowser.com/api/host` 里 `origin` 为 `https://ktv.lovbrowser.com`，`models.separator` 为 true
  - `/tv.html`、`/m.html` 为 200
- 本机 Clash / 代理可能把 Cloudflare HTTPS 握手掐掉。本机失败时改从 43 上 `curl https://ktv.lovbrowser.com/api/host` 判定。
- 不要把 `vendor/`、`data/`、曲库、`.env` 密钥打进镜像或提交进 git。
- 不要装 Torch / openai-whisper。分离只用 ONNX + onnxruntime。模型烤在 `/opt/lovktv/models`，不要放 `/app/data`，否则 `./data` 卷会盖住。
- 43 上 `8787` 已被别的 Node 占用。生产只绑 `127.0.0.1:8790`，由 Nginx 反代。不要把处理端端口暴露到 `0.0.0.0`。
- 证书复用 `/etc/ssl/lovbrowser/lovbrowser.com.pem`（和 `stock.lovbrowser.com` 一样）。浏览器看到的是 Cloudflare `*.lovbrowser.com`；源站这张是 CF 回源证书。
- DNS 在 Cloudflare 加 `CNAME ktv → lovbrowser.com`（橙云）。没有解析就不要当“部署失败”去改 Nginx。
- `LOVKTV_PUBLIC_URL=https://ktv.lovbrowser.com` 必须在 43 的 `~/lov-ktv/.env`。改 env 后要 recreate 容器。
- 网易试听/下载和 yt-dlp 走 43 上 lov-stock 的 Clash 边车：生产 compose 接 `lov-stock_default`，默认 `LOVKTV_HTTPS_PROXY=http://lov-stock-clash:7890`。不要设进程级 `HTTP_PROXY`，Mugen / Bilibili / OSS / 歌词不要进代理。Bilibili 走官方 search/view/playurl，不要用 yt-dlp 网页（容易 412）。Clash 没起来时先起 `lov-stock-clash`，不要另起一份订阅。
- 上线后不要打印微信密钥、Agent Key、OSS 密钥。检查只用 key 是否存在、长度。
- 成品媒体上阿里云 OSS（`lovktv/` 前缀），没配 OSS 就回退读本地 `data/media`。不要把曲库打进镜像或提交进 git。
- 43 的 `~/lov-ktv/.env` 复用 `/etc/lovbrowser/production.env` 里的 `ALIYUN_OSS_*`，并设 `LOVKTV_OSS_PREFIX=lovktv`，不要用 lovbrowser 的 `installPackage`。

## App 发版

- 版本写在仓库根 `VERSION`：`name=` 给人看，格式为 `YYYY.M.D.N`；其中 `N` 是当天的发版序号，每个自然日从 `1` 重新计数，不能沿用前一天的序号。`code=` 给 Android `versionCode`，格式为 `YYYYMMDDNN`，日期变化时每日序号归零但整体仍必须保持递增。
- 同一天发版递增 `N`；跨自然日发版将 `N` 重置为 `1`。不要为了保持旧序号而继续累加到下一天。
- **每次发版先按上述规则改 `VERSION`，提交后打 annotated tag `v{name}`，再推 tag。**

```bash
python scripts/version.py          # 看当前 name/code/tag
python scripts/version.py tag      # git tag -a v2026.8.30
git push origin HEAD --tags
```

- APK 不进 git、不进镜像。落在生产机 `data/apps/`，落地页读 `GET /api/apps`。电视/手机设置页显示 APK `versionName`。
- 下载：`https://ktv.lovbrowser.com/apps/tv.apk`、`/apps/phone.apk`。
- **直接打接口上传。不要 scp、不要 ssh 拷数据卷、不要另写上传流程。**
- 43 的 `~/lov-ktv/.env` 有 `LOVKTV_APP_UPLOAD_TOKEN`（不要打印、不要写进聊天）。本机读进环境变量后立刻：

```bash
python scripts/publish-apps.py
```

未指定 `--version` 时用 `VERSION` 的 `name`。未指定路径时用 Gradle 产物：电视 `android-tv/.../debug/app-debug.apk`，手机 `android-phone/.../release/app-release.apk`。
- 接口：`POST /api/apps/{tv|phone}`，`Authorization: Bearer`，multipart 字段 `file`，可选 `version`。默认 `https://ktv.lovbrowser.com`。
- 本机 Clash 掐 Cloudflare 时，只加一条隧道打同一接口（生产只绑 `127.0.0.1:8790`），不要改成别的办法：

```bash
ssh -o ExitOnForwardFailure=yes -N -L 18790:127.0.0.1:8790 ubuntu@43.134.133.185
python scripts/publish-apps.py --base http://127.0.0.1:18790
```

- 电视 APK 会烤进 `frontend/public`。重打前对 `android-tv` 跑 `:app:copyWebAssets assembleDebug --rerun-tasks`。

### Windows 打包环境

- Windows 本机统一使用 Android Studio 自带/已安装的 Java 21 与 Gradle 8.9；不要回退到 Gradle 8.5。当前 Gradle 路径为 `C:\Users\Administrator\Android\gradle-8.9`。
- 用户级环境变量应保持：`GRADLE_HOME=C:\Users\Administrator\Android\gradle-8.9`，`PATH` 包含 `%GRADLE_HOME%\bin`（或对应的绝对路径），`JAVA_HOME` 使用现有 Java 21。
- Gradle 8.x 在部分 Windows/JDK 组合下会在启动 Daemon 时报 `Unable to establish loopback connection`。构建前设置 `JAVA_TOOL_OPTIONS=-Djdk.net.unixdomain.tmpdir=C:\tmp`，并确保 `C:\tmp` 存在；新开终端后再运行 Gradle。
- 电视端先同步 Web 资源再打包；手机端直接打 Release：

```powershell
New-Item -ItemType Directory -Force C:\tmp | Out-Null
$env:JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:\tmp'

cd android-tv
gradle --no-daemon :app:copyWebAssets assembleDebug --rerun-tasks

cd ..\android-phone
gradle --no-daemon :app:assembleRelease
```

- 构建完成后用 Android SDK 的 `aapt dump badging` 核对两个 APK 的 `versionName` / `versionCode`，再按“App 发版”章节通过接口上传；APK 不提交 git。若 Gradle 仍报 loopback 错误，先确认终端已重启并实际使用 `gradle --version` 显示的 8.9。

## 产品边界

- 主路是搜歌名入库，不是先上传文件。
- 歌词优先官方 LRC；没有 Whisper 也能唱。
- Android TV 是局域网宿主 + 成品缓存，处理仍走这台处理端。
