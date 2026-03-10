# OpenClaw SaaS Platform

Management API, Web Console, Billing, and Metrics Exporter for OpenClaw on EKS.

## Components

| Component | Description | Tech |
|-----------|-------------|------|
| `api/` | Management API | Python FastAPI |
| `billing/` | Billing Worker (SQS consumer + Stripe) | Python |
| `metrics-exporter/` | Sidecar for Agent Pods | Python |
| `web-console/` | Frontend | React / Next.js |

## Architecture

See [openclaw-saas-contracts/docs/architecture.md](https://github.com/duchenxi/openclaw-saas-contracts/blob/main/docs/architecture.md)

## Documentation

| Doc | Description |
|-----|-------------|
| [Access Agent Web UI](docs/access-agent-webui.md) | 端口转发 + Gateway Token 访问 OpenClaw Control UI |
| [Channel Management](docs/channel-management.md) | 消息渠道绑定与区域过滤 |
| [Chromium Sidecar](docs/chromium-sidecar.md) | 浏览器自动化 Sidecar 配置 |
