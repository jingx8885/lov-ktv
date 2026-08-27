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
- 上线后不要打印微信密钥、Agent Key、OSS 密钥。检查只用 key 是否存在、长度。
- 成品媒体上阿里云 OSS（`lovktv/` 前缀），没配 OSS 就回退读本地 `data/media`。不要把曲库打进镜像或提交进 git。
- 43 的 `~/lov-ktv/.env` 复用 `/etc/lovbrowser/production.env` 里的 `ALIYUN_OSS_*`，并设 `LOVKTV_OSS_PREFIX=lovktv`，不要用 lovbrowser 的 `installPackage`。

## 产品边界

- 主路是搜歌名入库，不是先上传文件。
- 歌词优先官方 LRC；没有 Whisper 也能唱。
- Android TV 是局域网宿主 + 成品缓存，处理仍走这台处理端。
