# OpenClaw SaaS 平台架构 — 业务视角

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          用户触达层 (User-Facing)                        │
│                                                                         │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│   │   Telegram    │    │    飞书       │    │   Discord    │   ...更多    │
│   │   Bot API     │    │   App API    │    │   Bot API    │   渠道       │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘              │
│          │                   │                   │                       │
│          └───────────┬───────┴───────────────────┘                       │
│                      │ WebSocket 长连接                                   │
│                      ▼                                                   │
│   ┌─────────────────────────────────────────────────┐                    │
│   │          Agent Pods (每租户独立 Namespace)         │                    │
│   │                                                   │                    │
│   │   tenant-alice/          tenant-bob/               │                    │
│   │   ┌─────────────────┐   ┌─────────────────┐       │                    │
│   │   │  alice-agent-0  │   │  bob-agent-0    │       │                    │
│   │   │  ┌───────────┐  │   │  ┌───────────┐  │       │                    │
│   │   │  │ OpenClaw   │  │   │  │ OpenClaw   │  │       │                    │
│   │   │  │ (主容器)   │  │   │  │ (主容器)   │  │       │                    │
│   │   │  └───────────┘  │   │  └───────────┘  │       │                    │
│   │   │  ┌───────────┐  │   │  ┌───────────┐  │       │                    │
│   │   │  │ Metrics    │  │   │  │ Metrics    │  │       │                    │
│   │   │  │ Exporter   │──┼───│  │ Exporter   │──┼──► SQS│                    │
│   │   │  │ (Sidecar)  │  │   │  │ (Sidecar)  │  │       │                    │
│   │   │  └───────────┘  │   │  └───────────┘  │       │                    │
│   │   │  📦 PVC 10Gi    │   │  📦 PVC 10Gi    │       │                    │
│   │   └─────────────────┘   └─────────────────┘       │                    │
│   └─────────────────────────────────────────────────┘                    │
│                      │                                                   │
│                      │ LLM API 调用                                       │
│                      ▼                                                   │
│   ┌─────────────────────────────────────────────────┐                    │
│   │              LLM 供应商 (可选)                     │                    │
│   │   ┌──────────┐  ┌──────────┐  ┌──────────┐      │                    │
│   │   │ Amazon   │  │ OpenAI   │  │Anthropic │      │                    │
│   │   │ Bedrock  │  │ GPT-4    │  │ Claude   │      │                    │
│   │   │ (IRSA)   │  │ (API Key)│  │ (API Key)│      │                    │
│   │   └──────────┘  └──────────┘  └──────────┘      │                    │
│   └─────────────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        管理控制层 (Management Plane)                      │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────┐      │
│   │                    Web Console (React SPA)                    │      │
│   │   https://openclaw.chenxqdu.space/console                    │      │
│   │                                                              │      │
│   │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │      │
│   │   │ 登录注册  │ │ Agent    │ │ Billing  │ │ 日志查看  │       │      │
│   │   │          │ │ 创建管理  │ │ 用量配额  │ │          │       │      │
│   │   └──────────┘ └──────────┘ └──────────┘ └──────────┘       │      │
│   │                                                              │      │
│   │   Platform Admin: 全局总览 + 所有租户管理                      │      │
│   │   Tenant Owner:   自己租户的 Agent/渠道/用量                   │      │
│   └──────────────────────────────────────┬───────────────────────┘      │
│                                          │ REST API                      │
│                                          ▼                               │
│   ┌──────────────────────────────────────────────────────────────┐      │
│   │              Platform API (FastAPI × 2 副本)                  │      │
│   │              https://openclaw.chenxqdu.space/api/v1          │      │
│   │                                                              │      │
│   │   Auth         Tenant        Agent         Channel           │      │
│   │   ├ signup     ├ create      ├ create      ├ bind(telegram)  │      │
│   │   └ login      ├ delete      ├ delete      └ unbind          │      │
│   │   (JWT)        └ list        ├ config                        │      │
│   │                              ├ status      Billing           │      │
│   │   Admin                      └ logs        ├ quota           │      │
│   │   └ overview                               ├ usage           │      │
│   │     (全局统计)                               └ upgrade         │      │
│   └────────┬──────────────────┬──────────────────┬───────────────┘      │
│            │                  │                  │                        │
│            ▼                  ▼                  ▼                        │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐              │
│   │  PostgreSQL   │  │  K8s API     │  │  SQS              │              │
│   │  (RDS)        │  │  (EKS)       │  │  Usage Events     │              │
│   │              │  │              │  │                    │              │
│   │  users       │  │  Namespace   │  │  ┌──────────────┐ │              │
│   │  tenants     │  │  CRD CRUD    │  │  │ usage-events │ │              │
│   │  agents      │  │  Secret      │  │  │ (queue)      │ │              │
│   │  usage_events│  │  Pod/Logs    │  │  └──────┬───────┘ │              │
│   │  hourly_usage│  │              │  │         │         │              │
│   │  daily_usage │  │              │  │  ┌──────▼───────┐ │              │
│   │              │  │              │  │  │ usage-dlq    │ │              │
│   └──────────────┘  └──────────────┘  │  │ (dead letter)│ │              │
│                                       │  └──────────────┘ │              │
│                                       └──────────────────┘              │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        计费数据流 (Billing Pipeline)                      │
│                                                                         │
│   Agent Pod                    SQS                  Billing Consumer     │
│   ┌──────────┐            ┌──────────┐           ┌──────────────────┐   │
│   │ OpenClaw │─JSONL──►   │ Metrics  │──batch──► │                  │   │
│   │ 对话产生  │   文件     │ Exporter │  push     │  Consumer        │   │
│   │ token 用量│           │ Sidecar  │           │  (SQS → DB)      │   │
│   └──────────┘           └──────────┘           │                  │   │
│                                                  │  Aggregator      │   │
│                                                  │  (hourly/daily)  │   │
│                                                  └────────┬─────────┘   │
│                                                           │              │
│                                                           ▼              │
│                                                  ┌──────────────────┐   │
│                                                  │  PostgreSQL       │   │
│                                                  │  usage_events     │   │
│                                                  │  hourly_usage     │   │
│                                                  │  daily_usage      │   │
│                                                  └────────┬─────────┘   │
│                                                           │              │
│                                                           ▼              │
│                                                  ┌──────────────────┐   │
│                                                  │  Platform API     │   │
│                                                  │  GET /usage       │   │
│                                                  │  GET /billing     │   │
│                                                  │  GET /quota       │   │
│                                                  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 业务流程

### 1. 租户注册 → 创建 Agent → 开始使用

```
用户注册 ──► 创建 Tenant ──► 创建 Agent ──► 绑定渠道 ──► 开始对话
  │              │               │              │            │
  ▼              ▼               ▼              ▼            ▼
 users 表     K8s Namespace   CRD + Pod     Secret +     WebSocket
 JWT token    ResourceQuota   StatefulSet   CRD patch    连接渠道
              NetworkPolicy   PVC 10Gi
              LimitRange
```

### 2. 对话 → 计费全链路

```
终端用户发消息
  │
  ▼
Telegram/飞书/Discord ──WebSocket──► Agent Pod (OpenClaw)
  │                                      │
  │                                      ▼
  │                                LLM API 调用 (Bedrock/OpenAI/Anthropic)
  │                                      │
  │                                      ▼
  │                                回复写入 JSONL (含 token 用量)
  │                                      │
  │◄─────── 回复推送到渠道 ──────────────┘
  │                                      │
  │                               Metrics Exporter Sidecar
  │                               读取 JSONL (30s 周期)
  │                                      │
  │                                      ▼
  │                               SQS (usage events)
  │                                      │
  │                                      ▼
  │                               Billing Consumer
  │                               ├─ 写入 usage_events
  │                               └─ 聚合 hourly/daily
  │                                      │
  │                                      ▼
  │                               Web Console 展示用量
  │                               配额检查 (100K/1M/10M tokens)
```

### 3. 权限模型

```
┌─────────────────────────────────┐
│       Platform Admin            │
│   (SaaS 平台拥有者)              │
│                                 │
│   ✅ 看到所有 Tenant             │
│   ✅ 全局统计面板                 │
│   ✅ 管理所有资源                 │
└────────────┬────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌────────────┐  ┌────────────┐
│ Tenant A   │  │ Tenant B   │
│ Owner      │  │ Owner      │
│            │  │            │
│ ✅ Agent   │  │ ✅ Agent   │
│ ✅ Channel │  │ ✅ Channel │
│ ✅ Billing │  │ ✅ Billing │
│ ✅ Logs    │  │ ✅ Logs    │
│ ❌ 看不到 B │  │ ❌ 看不到 A │
└────────────┘  └────────────┘
```

## 套餐体系

| 套餐 | Token/月 | Max Agent | 内存/Agent | CPU/Agent | 月费 |
|------|----------|-----------|-----------|-----------|------|
| Free | 100K | 1 | 2Gi | 1 | $0 |
| Starter | 1M | 3 | 4Gi | 2 | $29 |
| Pro | 10M | 10 | 8Gi | 4 | $99 |
| Enterprise | 无限 | 无限 | 16Gi | 8 | 定制 |

## 技术栈总览

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | React + Vite | 暗色主题 SPA，FastAPI 托管 |
| API | Python FastAPI | JWT 认证，async，2 副本 |
| 容器编排 | EKS (K8s 1.30) | Graviton ARM64 节点 |
| Agent 运行时 | OpenClaw Operator | CRD 管理 StatefulSet |
| 数据库 | PostgreSQL 16 (RDS) | 用户/租户/用量数据 |
| 消息队列 | Amazon SQS | 用量事件 + DLQ |
| LLM | Bedrock (IRSA) / OpenAI / Anthropic | 多供应商支持 |
| 域名/SSL | Route53 + ACM | 可选自定义域名 |
| 负载均衡 | ALB + HTTPS | HTTP→HTTPS 301 重定向 |
| 镜像仓库 | ECR | 3 个仓库 |
| IaC | AWS CDK (Python) | 全参数化，一键部署 |
| 监控 | Prometheus Sidecar | :9090/metrics per agent |
