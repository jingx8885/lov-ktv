# lov-ktv Agent 原则

家庭 / 包厢自托管 KTV。处理端跑搜歌、人声分离、歌词对齐；电视或浏览器唱，手机扫码点歌。

## 上线

- 公网：`https://ktv.lovbrowser.com`
- 机器：`ubuntu@43.134.133.185`，目录 `~/lov-ktv`
- 发版来源：先提交并 `git push origin HEAD`，再在 43 上 `git pull`。仓库默认分支是 `master`；`main` 与 `master` 应对同一发版 commit，不要两边各写各的。
- 上线命令：

```bash
ssh ubuntu@43.134.133.185
cd ~/lov-ktv
git pull --ff-only origin master
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env up -d --build
```

- 只改 `frontend/public` 时，可先把静态文件拷进运行中的容器立刻见效，再 rebuild 让镜像与 git 一致：

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
- 上线后不要打印微信密钥、Agent Key。检查只用 key 是否存在、长度。
- 曲库仅供个人/家庭局域网。不要把 `data/media` 公开发布。

## 产品边界

- 主路是搜歌名入库，不是先上传文件。
- 歌词优先官方 LRC；没有 Whisper 也能唱。
- Android TV 是局域网宿主 + 成品缓存，处理仍走这台处理端。
