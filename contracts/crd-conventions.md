# CRD & Namespace Conventions

## Namespace 命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 租户 Namespace | `tenant-{name}` | `tenant-alice` |
| 控制面 | `control-plane` | |
| Operator | `openclaw-operator-system` | |
| 监控 | `monitoring` | |

## CRD Labels

```yaml
metadata:
  labels:
    app.kubernetes.io/managed-by: openclaw-saas
    openclaw-saas/tenant: "{tenant-name}"
    openclaw-saas/agent: "{agent-name}"
```

## Secret 命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 渠道凭证 | `{agent-name}-keys` | `alice-personal-keys` |

## Prometheus Metrics 命名

```
openclaw_tokens_input_total{tenant, agent, model}
openclaw_tokens_output_total{tenant, agent, model}
openclaw_llm_requests_total{tenant, agent, model, provider}
openclaw_sessions_active{tenant, agent}
openclaw_session_duration_seconds{tenant, agent}
```

## Agent Pod 资源要求（实测）

**OpenClaw 每个 Agent Pod 最低内存需求：2Gi**

Node.js 启动时堆内存约 500MB+，需要设置 `NODE_OPTIONS=--max-old-space-size=1536`。

| Plan | requests | limits | 最大 Agent 数 |
|------|----------|--------|---------------|
| free | 500m CPU / 2Gi Mem | 2 CPU / 4Gi Mem | 1 |
| pro | 500m CPU / 2Gi Mem | 2 CPU / 4Gi Mem | 5 |
| enterprise | 500m CPU / 2Gi Mem | 2 CPU / 4Gi Mem | 不限 |

### 节点规划

| 实例类型 | RAM | 可运行 Agent Pod 数 |
|----------|-----|-------------------|
| t4g.medium | 4GB | 1 |
| t4g.large | 8GB | 2-3 |
| m7g.medium | 4GB | 1 |
| m7g.large | 8GB | 2-3 |
