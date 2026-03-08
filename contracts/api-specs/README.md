# API Specifications

OpenAPI specs will be added here as the Management API is developed.

## Planned Endpoints

- `POST /api/v1/auth/signup` — 注册
- `POST /api/v1/auth/login` — 登录
- `GET /api/v1/tenants` — 租户列表
- `POST /api/v1/tenants` — 创建租户
- `DELETE /api/v1/tenants/{name}` — 删除租户
- `GET /api/v1/tenants/{name}/agents` — Agent 列表
- `POST /api/v1/tenants/{name}/agents` — 创建 Agent
- `PUT /api/v1/tenants/{name}/agents/{id}/config` — 更新配置
- `POST /api/v1/tenants/{name}/agents/{id}/channels` — 绑定渠道
- `DELETE /api/v1/tenants/{name}/agents/{id}/channels/{ch}` — 解绑渠道
- `GET /api/v1/tenants/{name}/agents/{id}/status` — Agent 状态
- `GET /api/v1/usage` — 用量统计
- `GET /api/v1/billing/subscription` — 订阅信息
- `POST /webhook/stripe` — Stripe 回调
