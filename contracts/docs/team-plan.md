# OpenClaw SaaS V3 — 两人分工方案（无 Router 精简版）

## 分工原则

1. **Operator 是黑盒** —— 不改源码，只用 CRD
2. **两人并行** —— Platform（业务层）和 Infra（基座层）完全独立
3. **Pod 自治** —— 每个 Pod 自己 WebSocket 连渠道，不需要中间路由层

---

## 👤 P1 — 平台工程师（管理 + 认证 + 计费 + 前端）

### 负责范围
> **用户注册 → 租户 Namespace → Agent CRUD → 渠道凭证 → 计费** — 面向 SaaS 用户的所有能力

### 核心模块

```
platform/
├── api/                         # Management API (Python FastAPI)
│   ├── main.py
│   ├── routers/
│   │   ├── auth.py              # 自建 JWT（注册/登录）
│   │   ├── tenants.py           # 租户 Namespace CRUD
│   │   ├── agents.py            # Agent CRD CRUD
│   │   ├── channels.py          # 渠道凭证管理（写入 K8s Secret + CRD config）
│   │   ├── usage.py             # 用量查询
│   │   └── billing.py           # 订阅 + 支付
│   ├── services/
│   │   ├── k8s_client.py        # K8s API 封装
│   │   │                        # - Namespace CRUD
│   │   │                        # - OpenClawInstance CRD CRUD
│   │   │                        # - Secret CRUD（渠道凭证）
│   │   │                        # - ResourceQuota / NetworkPolicy
│   │   ├── auth_svc.py          # JWT 签发 + 验证
│   │   ├── channel_svc.py       # 渠道配置构造
│   │   │                        # - 根据渠道类型生成 openclaw.json 片段
│   │   │                        # - 构造 Secret 环境变量
│   │   ├── stripe_svc.py        # Stripe 订阅
│   │   └── usage_svc.py         # 用量聚合
│   ├── models/
│   │   ├── user.py
│   │   ├── tenant.py
│   │   └── agent.py
│   ├── templates/               # K8s 资源模板
│   │   ├── namespace.yaml       # Namespace + labels
│   │   ├── resource_quota.yaml  # 按订阅等级的 quota
│   │   ├── network_policy.yaml  # 租户隔离策略
│   │   └── limit_range.yaml     # Pod 资源默认值
│   └── Dockerfile
│
├── billing/                     # Billing Worker
│   ├── consumer.py              # SQS 用量消费（Sidecar 推送的事件）
│   ├── aggregator.py            # 用量聚合（按租户/Agent/模型/时间）
│   ├── quota.py                 # 配额检查
│   └── Dockerfile
│
├── metrics-exporter/            # Metrics Exporter Sidecar（注入每个 Agent Pod）
│   ├── exporter.py              # 解析 sessions.json + JSONL
│   ├── prometheus.py            # 暴露 :9090/metrics
│   ├── sqs_pusher.py            # 推送用量事件到 SQS
│   ├── config.py                # TENANT_NAME / AGENT_NAME / SQS_URL
│   └── Dockerfile
│
├── web-console/                 # 前端 (React / Next.js)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── login.tsx
│   │   │   ├── dashboard.tsx    # Agent 列表 + 状态
│   │   │   ├── tenant/
│   │   │   │   └── settings.tsx
│   │   │   ├── agent/
│   │   │   │   ├── create.tsx   # 创建 Agent
│   │   │   │   ├── detail.tsx   # Agent 详情（Pod 状态、日志）
│   │   │   │   ├── config.tsx   # Agent 配置
│   │   │   │   └── channels.tsx # 渠道绑定
│   │   │   │       # ↑ 用户在这里填 Bot Token / App ID
│   │   │   │       #   → 调 API → 写入 Secret + CRD
│   │   │   │       #   → Operator reconcile → Pod 重启
│   │   │   │       #   → Pod 自动 WebSocket 连渠道
│   │   │   ├── billing.tsx
│   │   │   └── settings.tsx
│   │   └── components/
│   └── Dockerfile
│
└── helm/
    └── platform/
```

### 渠道配置核心逻辑

```python
# channel_svc.py — 渠道凭证 → CRD config + Secret

CHANNEL_TEMPLATES = {
    "telegram": {
        "secret_keys": ["TELEGRAM_BOT_TOKEN"],
        "config": {
            "channels": {
                "telegram": {
                    "enabled": True,
                    # Token 从环境变量自动读取
                }
            }
        }
    },
    "feishu": {
        "secret_keys": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
        "config": {
            "channels": {
                "feishu": {
                    "enabled": True,
                    "accounts": {
                        "default": {
                            # appId/appSecret 从环境变量注入
                        }
                    }
                }
            }
        }
    },
    "discord": {
        "secret_keys": ["DISCORD_BOT_TOKEN"],
        "config": {
            "channels": {
                "discord": {
                    "enabled": True,
                }
            }
        }
    },
}

async def bind_channel(tenant: str, agent: str, channel: str, credentials: dict):
    ns = f"tenant-{tenant}"
    secret_name = f"{agent}-keys"

    # 1. 更新 Secret（追加渠道凭证）
    await k8s.patch_secret(ns, secret_name, credentials)

    # 2. 更新 CRD config（追加渠道配置）
    template = CHANNEL_TEMPLATES[channel]
    await k8s.patch_crd_config(ns, agent, template["config"])

    # 3. Operator 检测到 CRD 变更 → 自动 reconcile → Pod 更新
```

### 对外接口

| 接口 | 说明 |
|------|------|
| `POST /api/v1/auth/signup` | 注册 |
| `POST /api/v1/auth/login` | 登录 |
| `GET /api/v1/tenants` | 我的租户列表 |
| `POST /api/v1/tenants` | 创建租户 |
| `DELETE /api/v1/tenants/{name}` | 删除租户 |
| `GET /api/v1/tenants/{name}/agents` | Agent 列表 |
| `POST /api/v1/tenants/{name}/agents` | 创建 Agent |
| `PUT /api/v1/tenants/{name}/agents/{id}/config` | 更新配置 |
| `POST /api/v1/tenants/{name}/agents/{id}/channels` | 绑定渠道 |
| `DELETE /api/v1/tenants/{name}/agents/{id}/channels/{ch}` | 解绑渠道 |
| `GET /api/v1/tenants/{name}/agents/{id}/status` | Agent 状态 |
| `GET /api/v1/usage` | 用量统计 |
| `GET /api/v1/billing/subscription` | 订阅信息 |
| `POST /webhook/stripe` | Stripe 回调 |

### 技术栈
- **后端**：Python (FastAPI + PyJWT + bcrypt + kubernetes client + prometheus_client)
- **Sidecar**：Python (轻量，解析 JSON/JSONL + Prometheus exporter + boto3 SQS)
- **前端**：React / Next.js
- **数据库**：PostgreSQL (RDS)
- **支付**：Stripe
- **部署**：Deployment (API ×2) + 静态站 (Console) + Sidecar (每个 Agent Pod)

---

## 👤 P2 — 基础设施工程师（IaC + EKS + 监控 + CI/CD）

### 负责范围
> **EKS 集群、AWS 服务、Operator 部署、监控、CI/CD** — 一切运行的基座

### 核心模块

```
infra/
├── cdk/                         # AWS CDK (Python)
│   ├── stacks/
│   │   ├── vpc.py               # VPC + 子网 + NAT + VPC Endpoints
│   │   ├── eks.py               # EKS 集群
│   │   ├── rds.py               # PostgreSQL (RDS)
│   │   ├── s3.py                # S3 桶
│   │   ├── cloudfront.py        # CloudFront + WAF（仅 Management API）
│   │   ├── sqs.py               # SQS 队列
│   │   ├── ecr.py               # ECR 仓库
│   │   └── iam.py               # IAM + Pod Identity
│   └── app.py
│
├── k8s-platform/
│   ├── namespaces/
│   │   ├── control-plane.yaml
│   │   └── monitoring.yaml
│   ├── operator/
│   │   └── values.yaml          # openclaw-operator Helm values
│   ├── karpenter/
│   │   ├── nodepool.yaml
│   │   └── ec2nodeclass.yaml
│   ├── storage/
│   │   └── storageclass.yaml    # EBS gp3
│   └── ingress/
│       └── alb-controller.yaml  # 仅管理面需要 ALB
│
├── observability/
│   ├── prometheus/
│   │   ├── values.yaml
│   │   └── rules/
│   ├── grafana/
│   │   └── dashboards/
│   │       ├── cluster-overview.json
│   │       ├── tenant-pods.json
│   │       └── cost-per-tenant.json
│   └── loki/
│       └── values.yaml
│
├── cicd/
│   ├── github-actions/
│   │   ├── ci.yaml
│   │   └── cd.yaml
│   └── argocd/
│       └── applications/
│
└── docs/
    ├── runbook.md
    └── disaster-recovery.md
```

### 技术栈
- **IaC**：CDK (Python)
- **K8s**：Helm + ArgoCD
- **监控**：kube-prometheus-stack
- **CI/CD**：GitHub Actions + ArgoCD

### 关键交付

| 交付物 | Week | 消费方 |
|--------|------|--------|
| EKS + VPC | W2 | P1 |
| Operator 部署 (Helm) | W2 | 所有 |
| RDS PostgreSQL | W2 | P1 |
| ECR + CI Pipeline | W2 | P1 |
| Karpenter + StorageClass | W3 | Operator |
| S3 + SQS | W3 | P1 |
| CloudFront + WAF + ALB | W3 | P1 |
| Pod Identity + RBAC | W3 | P1 |
| Prometheus + Grafana | W4 | 所有 |
| ArgoCD + CD Pipeline | W4 | P1 |

---

## 协作模型

```
         CRD + Namespace + Sidecar = 共享契约
         ┌────────────────────────────┐
         │  OpenClawInstance CRD Spec │
         │  Namespace 命名规范         │
         │  Secret 命名规范            │
         │  SQS Event Schema          │
         │  Sidecar 注入规范           │
         │  Prometheus Metrics 命名    │
         └──────────────┬─────────────┘
                        │
              ┌─────────┴─────────┐
              │                   │
              ▼                   ▼
      ┌───────────────┐   ┌───────────────┐
      │  P1 Platform  │   │  P2 Infra     │
      │               │   │               │
      │  JWT 认证     │   │  CDK (IaC)    │
      │  Namespace 管理│   │  EKS + K8s    │
      │  CRD CRUD     │   │  Operator 部署 │
      │  渠道凭证管理  │   │  RDS + S3     │
      │  Web Console  │   │  CI/CD        │
      │  Billing      │   │  监控          │
      └───────┬───────┘   └───────┬───────┘
              │                   │
              └──── K8s API ──────┘
                      ↕
            OpenClaw Operator
            (P2 部署，P1 使用)
```

---

## 时间线 (5 周 MVP)

| 周 | P1 Platform | P2 Infra |
|----|-------------|----------|
| **W1** | 🤝 定义：CRD 约定、Namespace 规范、API spec、Secret 命名 | 🤝 同上 + 开始 CDK |
| **W2** | FastAPI 骨架 + JWT 认证 + K8s client | EKS + VPC + RDS + Operator 部署 |
| **W3** | 租户 Namespace CRUD + Agent CRD CRUD + 渠道凭证管理 | Karpenter + S3 + SQS + CloudFront + ALB |
| **W4** | Web Console (Dashboard + Agent + 渠道配置) + Metrics Exporter Sidecar + Billing | Prometheus + Grafana + ArgoCD + CI/CD |
| **W5** | 🔗 全链路测试 + 文档 | 🔗 生产部署 + 负载测试 |

**比 V2 又省了 1 周（去掉 Router 开发和联调）。**

---

## 仓库结构

```
GitHub (duchenxi)
├── openclaw-saas-platform/     # P1 — Python + React
│   ├── api/
│   ├── billing/
│   ├── metrics-exporter/       # Sidecar 镜像
│   ├── web-console/
│   └── Dockerfile
│
├── openclaw-saas-infra/        # P2 — CDK + Helm values
│   ├── cdk/
│   ├── k8s-platform/
│   ├── observability/
│   └── cicd/
│
└── openclaw-saas-contracts/    # 共享 — 接口约定
    ├── api-specs/              # OpenAPI
    ├── crd-conventions.md      # CRD labels/annotations + Namespace/Secret 命名
    └── event-schemas/          # SQS 事件格式
```

---

## Phase 2 升级清单（规模化后）

当租户增长到 50+ 或遇到瓶颈时：

| 升级项 | 触发条件 | 工作量 |
|--------|---------|--------|
| 加 Router（Webhook 模式） | WebSocket 连接数瓶颈 | ~2 周 |
| 加 Redis | Router 需要路由缓存 | ~0.5 周 |
| OAuth2 / SSO | 企业客户要求 | ~1 周 |
| Kata VM 隔离 | 安全合规要求 | ~2 周 |
| 多区域部署 | 全球化需求 | ~3 周 |
