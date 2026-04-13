# OpenClaw SaaS on EKS — China Region (cn branch)

Multi-tenant OpenClaw SaaS platform for **AWS China Region** (cn-northwest-1, Ningxia).

> For Global (us-west-2), see [`main`](https://github.com/chenxqdu/openclaw-saas-gcr/tree/main).

## Architecture

| | Global (`main`) | China (`cn`) |
|---|---|---|
| **Region** | us-west-2 | cn-northwest-1 |
| **Account** | 956045422469 | 735091234506 |
| **Partition** | `aws` | `aws-cn` |
| **Default LLM** | bedrock-apikey | openai-compatible |
| **Agent image** | Upstream openclaw | Custom (pre-installed tools) |
| **Channels** | All | Feishu |
| **Service** | NLB + CloudFront | ClusterIP + ALB Ingress |
| **ECR** | Private (us-west-2) | **Private (cn-northwest-1)** |

## Deploy

### Prerequisites

AWS CLI (`--profile cn`), kubectl, helm, aws-cdk, jq, Docker with buildx

### 1. Configuration

```bash
cd infra && cp .env.example .env
# Fill ADMIN_EMAIL, ADMIN_PASSWORD, JWT_SECRET (required)
```

### 2. CDK Infrastructure

```bash
export AWS_PROFILE=cn CDK_DEFAULT_ACCOUNT=735091234506 CDK_DEFAULT_REGION=cn-northwest-1
cd infra/cdk && cdk deploy --all --require-approval never
```

Stacks: vpc, ecr, sqs, s3, eks (K8s 1.30, Graviton), iam, rds (PostgreSQL)

### 3. Build & Push Images

> **⚠️ CN branch → Private ECR only.** Public ECR is only for cn-workshop.

```bash
aws ecr get-login-password --region cn-northwest-1 --profile cn | \
  docker login --username AWS --password-stdin 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn

docker buildx build --platform linux/arm64 \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-platform:v$(cat platform/VERSION) \
  --push platform/

docker buildx build --platform linux/arm64 \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-metrics-exporter:v$(cat platform/metrics-exporter/VERSION) \
  --push platform/metrics-exporter/

docker buildx build --platform linux/arm64 \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-billing-consumer:v$(cat platform/billing/VERSION) \
  --push platform/billing/
```

### 4. K8s Deployment

```bash
aws eks update-kubeconfig --name openclaw-saas-cluster --region cn-northwest-1 --profile cn
cd infra && ./scripts/deploy.sh --skip-cdk
```

### 5. Verify

```bash
kubectl port-forward -n openclaw-platform svc/platform-api 8000:8000
curl http://localhost:8000/health
# {"status":"ok","version":"0.9.42"}
```

## Current Deployment

| Component | Status | Details |
|-----------|--------|---------|
| EKS | ✅ | `openclaw-saas-cluster`, K8s 1.30, 2× Graviton |
| Platform API | ✅ | `v0.9.42` (CN private ECR) |
| Operator | ✅ | v0.20.0 |
| ALB Controller | ✅ | 2 replicas |
| RDS | ✅ | PostgreSQL t4g.micro |

## Custom Agent Image

Pre-installs tools blocked by China firewall: acpx, claude-agent-acp, kiro-cli, jq.

```bash
cd custom-image
docker buildx build --platform linux/arm64 \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-custom-cn:latest --push .
```

## Branch Workflow

```
main (Global) → cn (China) → cn-workshop
```

Generic fixes cherry-pick `main → cn`. CN-specific stays on `cn`. Never reverse-merge.
