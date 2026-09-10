# lov-ktv 数据表

线上用 PostgreSQL（Supabase），本机和 pytest 用 SQLite。连接串：`LOVKTV_DATABASE_URL` 或 `DATABASE_URL`。空则写 `data/lovktv.sqlite`。测试里改 `store.DB_PATH` 时始终走 SQLite。

媒体、歌词、时间轴仍在 `data/media/{song_id}/` 或 OSS，不进库。

## 表

| 表 | 用途 |
|---|---|
| `songs` | 曲库元数据与处理状态 |
| `rooms` | 包厢 / 房间播放状态 |
| `queue` | 房间点歌队列 |
| `users` | 微信、密码账号或本机设备身份 |
| `sessions` | 登录 cookie |
| `login_tickets` | 电视扫码登录票 |
| `hosts` | 本机 / UA 与房间的绑定 |
| `guest_song_counts` | 未登录每天免费入库次数 |
| `point_wallets` | 积分余额 |
| `point_ledger` | 积分流水 |
| `ad_sessions` | 开屏 / 等待广告观看 |
| `point_claims` | 注册 / 下载一次性奖励 |
| `learn_words` | 全局词状态：熟练度、砍词、掌握 |
| `learn_word_sources` | 词与歌的来源关联 |
| `learn_migrations` | 旧 `learn_cards` 惰性合并标记 |

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
| username | TEXT | 登录名，可空；房间号或自定义 |
| username_key | TEXT | 小写用户名，非空时唯一 |
| password_hash | TEXT | `pbkdf2_sha256`，无密码账号为空 |
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

主键 `(guest_key, day)`。有用户名或微信的账号不限。游客免费 5 首用完后按积分扣。

### learn_progress / learn_mastery / learn_mistakes / learn_submissions

游戏课程进度、知识点掌握、错题和提交幂等记录。进度主键为
（owner, song_id, unit_id, skill），掌握主键为（owner, song_id, kind, item_key），
错题主键为（owner, song_id, qkind, item_key），提交主键为
（owner, song_id, attempt_id）。attempt_id 用于防止同一轮练习重复计入。

### learn_words / learn_word_sources / learn_migrations

背词的唯一词库。`learn_words` 主键为（owner, word_id），`word_id` 是
`sha1(语言 + 规范化词形)`，**不含 song_id**——同一个词在不同歌之间共享熟练度
（stage / reps / due_at）和砍词状态（`skipped_at`），达到最后一个盒子后写
`retired_at` 表示已掌握，不再出题。砍词是持久状态而不是删除，可以恢复。

`learn_word_sources` 主键为（owner, word_id, song_id），保存歌词行与时间区间。
歌曲专属复习靠它做范围过滤，跨歌牌组用最近一条做听辨题和详情卡的锚点。

`learn_cards` 降级为只读历史。首次访问词库时按 owner 惰性合并一次，同一个词的
多张旧卡取 `max(stage)` / `max(reps)` / `min(due_at)`，合并过的 owner 记在
`learn_migrations`（kind 为 `cards_to_words`）。

### point_wallets / point_ledger / ad_sessions / point_claims

积分：点歌 −1，处理歌 −5，看满 30 秒广告 +1，注册 +10，下载 App +10。钱包 `owner` 为 `u:` 用户或 `m:` 机器号。广告 token 服务端计时，未满 30 秒不能领。

## Supabase

1. SQL Editor 执行 `docs/schema.postgres.sql`。
2. 用 **Session pooler** 连接串（端口 `6543`），不要把 anon key 当数据库密码。
3. 后端直连，不走 PostgREST；不必开 RLS。
4. 43 的 `~/lov-ktv/.env` 加 `LOVKTV_DATABASE_URL=...`，再 recreate 容器。
