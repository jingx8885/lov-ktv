# lov-ktv API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/host` | 局域网入口 `{origin,process_origin,mode,phone_path,cache_ready,database}` |
| GET | `/api/search?q=` | tonzhon / 网易搜歌 |
| POST | `/api/songs/import` | `{query,id,title,artist,language}` 下载入库 |
| POST | `/api/songs` | multipart 本地上传（后备） |
| GET | `/api/songs` | 曲库 |
| GET | `/api/songs/{id}` | 含文件列表 |
| GET | `/api/rooms` | 本机记住的房间；没有则 `{code:""}` |
| POST | `/api/rooms` | 开房；同一机器 / UA 会回到上次的房 |
| GET | `/api/rooms/{code}` | 房间快照，并记住本机 |
| POST | `/api/rooms/{code}/queue` | `{song_id}` 点歌（1 积分） |
| POST | `/api/rooms/{code}/bump` | `{id}` 顶歌 |
| POST | `/api/rooms/{code}/skip` | 切歌 |
| POST | `/api/rooms/{code}/mix` | `{vocal_mix,volume}` |
| GET | `/api/auth/status` | 微信 / 扫码 / 密码登录是否可用；`guest_limit` |
| GET | `/api/auth/me` | 当前用户 + `quota` + `points` |
| POST | `/api/auth/login` | `{username,password}` 一键登录 |
| POST | `/api/auth/register` | `{username,password}` 一键注册并登录；送 10 积分 |
| GET | `/api/points` | 积分余额与规则 |
| GET | `/api/ads?placement=` | `splash` / `wait` 广告 |
| POST | `/api/ads/start` | `{placement}` 开一条广告，看 30 秒 |
| POST | `/api/ads/click` | `{token}` 手机跳转落地页 |
| POST | `/api/ads/complete` | `{token}` 看满 30 秒 +1 积分 |
| POST | `/api/points/claim` | `{kind:download}` 安装 App +10，只能领一次 |
| POST | `/api/admin/login` | `{token}` 管理令牌；Cookie `lovktv_admin`。令牌来自 `LOVKTV_ADMIN_TOKEN`（可复用上传令牌） |
| GET | `/api/admin/me` | 管理会话是否有效 |
| GET | `/api/admin/summary` | 账号/曲库/房间/积分汇总与规则 |
| GET | `/api/admin/users` | 账号列表，含余额 |
| GET | `/api/admin/points?q=` | 查钱包与流水 |
| POST | `/api/admin/points` | `{username\|owner, delta, note}` 加分或扣分，`delta` 负数为扣 |
| POST | `/api/admin/recharge` | `{username\|owner, amount, note}` 充值，amount 必须为正 |
| GET | `/api/admin/recharges` | 充值记录 |
| POST | `/api/admin/users` | `{username,password,nickname}` 开号 |
| POST | `/api/admin/users/{id}` | `{nickname,password}` 改昵称/密码 |
| GET | `/api/admin/songs` | 曲库 `?q=`；`POST /import` 入库；`POST /{id}` 改歌名；删除/重试 |
| GET | `/api/admin/rooms` | 房间列表 `?q=` |
| POST | `/api/admin/rooms` | `{code}` 开房，空码自动生成 |
| GET | `/api/admin/rooms/{code}` | 房间快照与队列 |
| DELETE | `/api/admin/rooms/{code}` | 删房（队列一并清） |
| POST | `/api/admin/rooms/{code}/queue` | `{song_id}` 管理端点歌，不扣积分 |
| POST | `/api/admin/rooms/{code}/bump` | `{id}` 顶歌 |
| POST | `/api/admin/rooms/{code}/play` | `{id}` 切到这首 |
| POST | `/api/admin/rooms/{code}/skip` | 切歌 |
| POST | `/api/admin/rooms/{code}/clear` | 清空队列 |
| DELETE | `/api/admin/rooms/{code}/queue/{id}` | 移出一首 |
| GET | `/api/admin/ads` | 当前开屏/等待广告 |
| POST | `/api/admin/logout` | 退出管理 |
| POST | `/api/auth/logout` | 退出 |
| POST | `/api/auth/device` | `{device_id,nickname}` 本机身份（无微信凭证时） |
| GET | `/api/auth/wechat/login` | 微信登录；`quick=1` 为微信内快捷登录 |
| GET | `/api/auth/wechat/callback` | 微信 OAuth 回调 |
| POST | `/api/auth/qr` | 电视扫码票 `{room}` |
| GET | `/api/auth/qr/{ticket}` | 票状态；`claim=1` 时电视领取会话 |
| POST | `/api/auth/qr/{ticket}/confirm` | 手机确认电视登录 |
| WS | `/ws/rooms/{code}` | 实时快照 |
| GET | `/media/{song_id}/{file}` | 媒体 |

管理端：`/admin.html`。用 `LOVKTV_ADMIN_TOKEN`（没有则用 `LOVKTV_APP_UPLOAD_TOKEN`）进入。积分加减尤其是扣分走这里。

登录页：`/login.html`。Cookie：`lovktv_session`。主路是用户名 + 密码，用户名默认可填房间号。积分扣费默认关闭（`LOVKTV_POINTS=1` 才扣：处理歌 5 分、点歌 1 分）。看 30 秒广告 +1，注册或下载 App 各 +10。未配置微信时仍可用本机身份 + 电视扫码。微信需 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`，公众号快捷登录另配 `WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET`，公网回调 `LOVKTV_PUBLIC_URL`。

媒体目录：`data/media/{song_id}/original.mp3`、`lyrics.lrc`、`lyrics.json`、`karaoke.m4a`、`guide.m4a`。
