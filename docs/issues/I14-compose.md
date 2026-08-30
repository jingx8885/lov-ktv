# I14 · Compose 一键启动

Epic: E07  
depends_on: I05, I08, I11, I12

## 合同

`docker compose up --build` 启动处理端（API + 任务线程 + 静态页），挂载 `data/`。  
镜像只打 `backend` / `frontend`，不含 `vendor`、`android-tv`、本地曲库。  
人声分离 ONNX（`UVR_MDXNET_KARA_2.onnx` + onnxruntime）和无 Torch 的
`faster-whisper` small 模型烤在 `/opt/lovktv/models`，不放进 `data/` 挂载点。
不装 Torch 或 `openai-whisper`；Whisper 不可用时仍保留 onset 回退。

电视盒子填 `http://宿主机局域网IP:8787` 作为处理服务器。

## 验收

- 端口 `8787`，健康检查 `GET /api/host`。
- `docker compose up --build` 后可打开 `/tv.html` 与 `/m.html`。
