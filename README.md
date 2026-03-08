# OpenClaw SaaS on EKS

Multi-tenant OpenClaw SaaS platform running on Amazon EKS.

## Structure

```
platform/    - Management API + Web Console + Billing + Metrics Exporter
infra/       - CDK IaC + Helm + K8s manifests + Monitoring + CI/CD
contracts/   - Shared contracts: API specs, CRD conventions, event schemas
```

## Architecture

- **EKS** (K8s 1.30, Graviton arm64) — us-west-2
- **RDS PostgreSQL** — tenant/agent/billing data
- **K8s Operator** — OpenClaw instance lifecycle management
- **Per-tenant namespace isolation** with ResourceQuota + NetworkPolicy + LimitRange
- **Bedrock IRSA** — platform-managed LLM access (no API keys needed)
- **Metrics pipeline** — Prometheus sidecar → SQS → Billing aggregator

## Live

https://openclaw.chenxqdu.space
