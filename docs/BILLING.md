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

## Google 登录

在 Google Cloud Console 创建 Web client，配置授权来源为正式站点，并设置：

```env
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

登录页通过 Google Identity Services 获取凭证，服务端向 Google `tokeninfo` 校验受众、签发方和已验证邮箱后才创建会话。
