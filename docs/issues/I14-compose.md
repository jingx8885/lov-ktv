# I14 · Compose 一键启动

Epic: E07  
depends_on: I05, I08, I11, I12

## 合同

`docker compose up --build` 启动处理端（API + 任务线程 + 静态页），挂载 `data/`。  
镜像只打 `backend` / `frontend`，不含 `vendor`、`android-tv`、本地曲库。

电视盒子填 `http://宿主机局域网IP:8787` 作为处理服务器。

## 验收

- 端口 `8787`，健康检查 `GET /api/host`。
- `docker compose up --build` 后可打开 `/tv.html` 与 `/m.html`。
