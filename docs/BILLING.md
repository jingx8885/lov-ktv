# lov-ktv 商业化配置

## 套餐

- 免费账号：登录后可继续使用基础处理能力；处理队列优先级为 0，最多 1 个房间。历史免费账号保留无限处理；付费订阅取消、暂停或欠费后回退为每月 20 首额度。
- 入门包月（5 USD/月）：每月 100 首处理额度、标准处理队列、1 个房间。
- 畅唱包月（20 USD/月）：每月 1000 首处理额度、优先处理队列、最多 5 个房间。
- 管理员账号（`jingxu8885` / `jingxu8885@gmail.com`）：内部无限制权益，不消耗月度处理额度、不受房间数量限制，并使用最高处理优先级。

处理额度按上海时区自然月统计。Stripe 订阅处于 `active` 或 `trialing` 状态时才授予付费权益；取消、暂停、欠款和过期状态会回退到免费账号的每月 20 首额度。

## Stripe

在 Stripe Dashboard 创建两个 recurring / monthly Price，然后写入生产环境：

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_5=price_...
STRIPE_PRICE_20=price_...
```

当前生产账户（joycut）已创建的月付价格：

- 入门包月：`price_1UF7bv2KGesDuiQCnZzAeS2S`
- 畅唱包月：`price_1UF7bw2KGesDuiQCW1g7QNqa`

Webhook 地址：`https://ktv.lovbrowser.com/api/billing/webhook`。至少勾选：

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `customer.subscription.paused`
- `invoice.paid`
- `invoice.payment_failed`

Webhook 使用签名校验和事件去重表，重复投递不会重复开通权益。用户可从 `/billing.html` 进入 Stripe Customer Portal 管理订阅和付款方式。

## Android Google Play 订阅

Google Play 分发的手机 App 使用 Play Billing，产品 ID 固定为：

- `starter_monthly`：$5 / 月
- `pro_monthly`：$20 / 月

在 Play Console 中为每个产品创建月度 base plan。手机 App 会查询产品、拉起 Google Play 购买页、确认购买并把 purchase token 发到 `/api/billing/google-play/verify`。服务端必须使用 Google Play Developer API 校验 token，不能只信任客户端回调。

生产环境配置：

```text
GOOGLE_PLAY_PACKAGE=com.lovktv.phone
GOOGLE_PLAY_SERVICE_ACCOUNT_FILE=/run/secrets/google-play-service-account.json
```

服务账号只授予 Play Console 的订阅查看权限，不要把 JSON 密钥提交到 Git 或写进镜像。续费、退款、暂停和取消应再接入 Google Play Real-time Developer Notifications（Pub/Sub），定期同步订阅状态。

## 转化漏斗（第一方埋点）

- 表：`funnel_events`（SQLite/Postgres 同一 DDL），字段 `kind / owner / day(上海时区) / meta / created_at`。
- 事件：`landing_view`（落地页 beacon，带 utm/ref）、`cta_tv`、`cta_phone`、`song_search`、`song_queued`（搜歌入库或上传）、`signup`/`login`（Google / LovBrowser / 密码）、`checkout_start`、`paid`、`sub_status`。
- `POST /api/funnel` 只收白名单 kind（landing_view / cta_tv / cta_phone），meta 只透传 utm_* / ref / lang，防止被当垃圾日志端点。
- 查看：管理页 `admin.html` 顶部第二行（`/api/admin/summary` 里的 `funnel` 字段），或容器里 `python -c "from lovktv.storage import store; print(store.funnel_summary(30)['by_kind'])"`。
- 隐私：不写 IP、不写搜索词；privacy.html 已披露“匿名产品使用统计”。

## Google 登录

在 Google Cloud Console 创建 Web client，配置授权来源为正式站点，并设置：

```env
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

登录页通过 Google Identity Services 获取凭证，服务端向 Google `tokeninfo` 校验受众、签发方和已验证邮箱后才创建会话。
