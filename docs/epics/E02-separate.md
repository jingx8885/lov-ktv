# E02 · 上传、分离与封装

目标：用户上传任意歌曲后，服务器产出可唱的伴奏、人声和双音轨媒体。

## Issues

- I03 搜歌下载入库（主）与本地上传（备）
- I04 人声分离适配器
- I05 双音轨封装与媒体网关

## 汇总验收

- 上传后出现 job，状态从 queued → separating → ready / failed。
- ready 歌曲至少有 `instrumental`、`vocals`、可播放媒体 URL。
- 分离优先 audio-separator；无 GPU 时明确降级并写进 job 日志，不得假装成功。
