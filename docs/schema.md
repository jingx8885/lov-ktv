# lov-ktv 数据表

线上用 PostgreSQL（Supabase），本机和 pytest 用 SQLite。连接串：`LOVKTV_DATABASE_URL` 或 `DATABASE_URL`。空则写 `data/lovktv.sqlite`。测试里改 `store.DB_PATH` 时始终走 SQLite。

媒体、歌词、时间轴仍在 `data/media/{song_id}/` 或 OSS，不进库。

## 表

| 表 | 用途 |
|---|---|
| `songs` | 曲库元数据与处理状态 |
| `rooms` | 包厢 / 房间播放状态 |
| `queue` | 房间点歌队列 |
| `users` | 微信或本机设备身份 |
| `sessions` | 登录 cookie |
| `login_tickets` | 电视扫码登录票 |
| `hosts` | 本机 / UA 与房间的绑定 |
| `guest_song_counts` | 未登录每天点歌次数 |

### songs

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 12 位 hex |
| title | TEXT | 歌名 |
| artist | TEXT | 歌手，默认空 |
| language | TEXT | `zh` / `ja` / `en` |
| status | TEXT | `queued` `fetching` `separating` `aligning` `annotating` `composing` `ready` `failed` |
| error | TEXT | 失败或降级说明 |
| audio_source | TEXT | `netease` / `bilibili` / `mugen` / `youtube` 等 |
| netease_id | TEXT | 网易 id，或 Mugen kid |
| created_at | BIGINT | 纪元毫秒（SQLite 为 INTEGER） |

### rooms

| 列 | 类型 | 说明 |
|---|---|---|
| code | TEXT PK | 房间码，大写 |
| created_at | BIGINT | 纪元毫秒 |
| vocal_mix | DOUBLE | 0–1，原唱/伴唱 |
| volume | INTEGER | 0–100 |
| mic_gain | INTEGER | 0–100 |
| lyric_mode | TEXT | `ja` / `zh` / `roma` / `all` |
| now_index | INTEGER | 当前唱到队列第几首 |

### queue

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 队列项 id |
| room | TEXT | `rooms.code` |
| song_id | TEXT | `songs.id` |
| position | INTEGER | 排序，越小越前 |
| created_at | BIGINT | 纪元毫秒 |

### users

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 用户 id |
| wechat_openid | TEXT | 微信 openid，可空串 |
| wechat_unionid | TEXT | 微信 unionid |
| device_id | TEXT | 本机身份 |
| nickname | TEXT | 显示名 |
| avatar | TEXT | 头像 URL |
| created_at | BIGINT | 纪元毫秒 |

### sessions

| 列 | 类型 | 说明 |
|---|---|---|
| token | TEXT PK | cookie `lovktv_session` |
| user_id | TEXT | `users.id` |
| created_at | BIGINT | 纪元毫秒 |
| expires_at | BIGINT | 纪元毫秒 |

### hosts

| 列 | 类型 | 说明 |
|---|---|---|
| key | TEXT PK | `m:` 机器号或 `u:` UA+IP 指纹 |
| room | TEXT | `rooms.code` |
| ua | TEXT | 最近一次 User-Agent |
| created_at | BIGINT | 纪元毫秒 |
| last_seen | BIGINT | 纪元毫秒 |

### login_tickets

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 二维码票 |
| status | TEXT | `pending` `confirmed` `expired` `used` |
| user_id | TEXT | 确认后写入 |
| created_at | BIGINT | 纪元毫秒 |
| expires_at | BIGINT | 默认 180s |

### guest_song_counts

| 列 | 类型 | 说明 |
|---|---|---|
| guest_key | TEXT | `u:` 游客用户 / `h:` 宿主 cookie / `g:` IP+UA |
| day | TEXT | `YYYY-MM-DD`（东八区） |
| used | INTEGER | 当天已点歌数 |

主键 `(guest_key, day)`。有用户名或微信的账号不限。

## Supabase

1. SQL Editor 执行 `docs/schema.postgres.sql`。
2. 用 **Session pooler** 连接串（端口 `6543`），不要把 anon key 当数据库密码。
3. 后端直连，不走 PostgREST；不必开 RLS。
4. 43 的 `~/lov-ktv/.env` 加 `LOVKTV_DATABASE_URL=...`，再 recreate 容器。
