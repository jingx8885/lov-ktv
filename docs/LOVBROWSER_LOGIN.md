# LovBrowser 统一登录上线清单

KTV 采用 OIDC Authorization Code + PKCE。浏览器只接触 KTV 的 `lovktv_session` HttpOnly Cookie；授权码、client secret 和 userinfo 交换均在后端完成。KTV 不直连、不猜测 LovBrowser 的 `t_users` 表结构。

边界说明：LovBrowser 当前 Web 客户端把 JWT 保存在各自 origin 的 `localStorage`，并非可由子域共享的 Cookie；在不修改主站的前提下，不能安全地让 KTV 的本地 session 反向写入主站登录态。OIDC 能保证“主站已登录 → KTV 免重复输入凭据”，但“KTV 本地密码登录 → 回主站仍登录”不成立。若产品必须双向统一，需要主站提供同一 OIDC client/受信任的 token broker（或把主站会话迁移为限定 `.lovbrowser.com` 的 Secure、HttpOnly、SameSite Cookie），并由主站负责统一 logout；本项目不擅自改主站或共享其数据库。

## 主站前置条件

1. 在 LovBrowser OIDC 管理接口登记 client，回调 URI 精确填写 `https://ktv.lovbrowser.com/api/auth/lovbrowser/callback`，允许 `openid profile email` scope，并启用 PKCE。
2. 保存一次性返回的 client secret，仅写入生产 `.env`，不要提交或打印。
3. 确认 issuer 的 discovery 可访问：`${LOVBROWSER_OIDC_ISSUER}/.well-known/openid-configuration`，且包含 authorization/token/userinfo 三个 HTTPS 端点。

## KTV 环境变量

`LOVBROWSER_OIDC_ISSUER`、`LOVBROWSER_OIDC_CLIENT_ID`、`LOVBROWSER_OIDC_CLIENT_SECRET`、`LOVBROWSER_OIDC_STATE_SECRET`（稳定随机值）和可选 `LOVBROWSER_OIDC_SCOPES`。若 discovery 路径非 issuer 默认路径，再设置 `LOVBROWSER_OIDC_DISCOVERY_URL`。

首次启动会把 `users.lovbrowser_sub` 做幂等增量迁移并建立唯一索引；不需要共享数据库或跨项目迁移。一个 OIDC subject 始终映射到一个 KTV 用户；仅当 OIDC 返回 `email_verified=true` 时才用邮箱做首次关联/展示，邮箱不作为身份主键。

## 验证清单

```bash
curl -fsS https://ktv.lovbrowser.com/api/auth/status
curl -I 'https://ktv.lovbrowser.com/api/auth/lovbrowser/login?next=/m.html'
```

浏览器验收：

- 已登录 LovBrowser 用户访问登录链接，授权后回到 `/m.html`，`GET /api/auth/me` 返回 `user.lovbrowser=true`；刷新仍保持会话。
- 错误凭据由主站拒绝，不在 KTV 建立会话；取消授权回调返回 400。
- 篡改/缺失 state、过期 code、userinfo 无 `sub` 均不建立会话；回调错误不会把 `next` 重定向到外域。
- `POST /api/auth/logout` 后 `/api/auth/me` 的 user 为 null；删除/过期 KTV session 后受保护 API 返回 401 或登录跳转。
- 从非白名单 redirect URI 发起授权必须被主站拒绝；生产反向代理需传 `X-Forwarded-Proto: https`，确保 Cookie 带 `Secure`。

本地自动化覆盖 state 签名/next 白名单、OIDC discovery/token/userinfo 成功和失败、用户幂等映射及 session/logout；真实主站登录、生产域名回调和跨浏览器 Cookie 仍需上线前人工验收。
