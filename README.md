# OpenClaw SaaS on EKS — China Region

Multi-tenant OpenClaw SaaS platform for **AWS China Region** (cn-northwest-1, Ningxia).

> For Global (us-west-2), see [`main`](https://github.com/chenxqdu/openclaw-saas-gcr/tree/main).

## Architecture

```
                    Internet
                       │
                   NLB (TCP)
                       │
                ┌──────┴──────┐
                │  EKS Cluster │
                │  (Graviton)  │
                └──────┬──────┘
         ┌─────────────┼─────────────┐
         │             │             │
   ┌─────┴─────┐  ┌───┴───┐  ┌─────┴─────┐
   │ Platform   │  │Operator│  │  Tenant   │
   │ API + UI   │  │(Helm)  │  │ Namespaces│
   └─────┬─────┘  └───┬───┘  └─────┬─────┘
         │             │             │
         │        Creates CRD   ┌───┴────────┐
         │             │        │ Agent Pod   │
         │             └──────► │ ├ openclaw  │
         │                      │ ├ otel-coll.│
         │                      │ ├ metrics-  │
         │                      │ │ exporter  │
         │                      │ └ gw-proxy  │
    ┌────┴────┐                 └───┬────────┘
    │ RDS     │                     │
    │ Postgres│              otel-collector
    └─────────┘              :9090/metrics
         │                          │
    ┌────┴────┐              ┌──────┴──────┐
    │ SQS     │◄─────────────│metrics-exp. │
    │ Queue   │  usage deltas│(scrape+push)│
    └────┬────┘              └─────────────┘
         │
    ┌────┴────┐
    │ Billing │
    │Consumer │
    └─────────┘
```

| | Global (`main`) | China (`cn`) |
|---|---|---|
| **Region** | us-west-2 | cn-northwest-1 |
| **Account** | 956045422469 | 735091234506 |
| **Partition** | `aws` | `aws-cn` |
| **Default LLM** | bedrock-irsa (no key needed) | openai-compatible |
| **Agent Image** | Upstream openclaw | Custom (pre-installed tools) |
| **Channels** | All | Feishu |
| **Ingress** | NLB + CloudFront | NLB |
| **ECR** | Private (us-west-2) | Private (cn-northwest-1) |

## Quick Start

### 1. Configure Environment

```bash
cd infra

# Use the pre-filled CN template:
cp .env.cn .env

# Fill in required credentials:
vim .env    # Set ADMIN_PASSWORD, JWT_SECRET
```

All deployment config lives in `.env`. No hardcoded values elsewhere.

### 2. Deploy Infrastructure (CDK)

> **⚠️ Critical:** Always set `AWS_DEFAULT_REGION` explicitly. CDK CLI uses the default AWS profile's region, not `--profile`'s region. The `aws_region` context in `cdk.json` is the reliable override.

```bash
export AWS_PROFILE=cn
export AWS_DEFAULT_REGION=cn-northwest-1

cd infra/cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap (first time only)
cdk bootstrap aws://${AWS_ACCOUNT_ID}/${AWS_DEFAULT_REGION}

# Deploy step by step (recommended over --all to avoid OOM):
cdk deploy openclaw-saas-vpc --require-approval never
cdk deploy openclaw-saas-ecr openclaw-saas-sqs openclaw-saas-s3 --require-approval never --concurrency 3
cdk deploy openclaw-saas-eks --require-approval never                    # ~15 min
cdk deploy openclaw-saas-iam openclaw-saas-rds --require-approval never --concurrency 2
```

**CDK Stacks:** vpc, ecr, sqs, s3, eks (K8s 1.30, 2× Graviton t4g.medium), iam, rds (PostgreSQL t4g.micro)

### 3. EKS Access Setup

CDK creates the EKS cluster with a Lambda-managed IAM role. Your IAM user needs to assume that role:

```bash
# Get the creation role ARN from CDK output
CREATION_ROLE=$(aws cloudformation describe-stacks \
  --stack-name openclaw-saas-eks --region ${AWS_DEFAULT_REGION} --profile ${AWS_PROFILE} \
  --query 'Stacks[0].Outputs[?OutputKey==`KubectlRoleArn`].OutputValue' --output text)

# Configure kubectl
aws eks update-kubeconfig \
  --name openclaw-saas-cluster --region ${AWS_DEFAULT_REGION} \
  --profile ${AWS_PROFILE} --role-arn "${CREATION_ROLE}"

# Verify
kubectl get nodes
```

### 4. Mirror Upstream Images to CN ECR

CN nodes cannot pull from Docker Hub / ghcr.io. All images the operator uses must be
mirrored into CN ECR **before** deploying any agent. The operator's `spec.registry`
field rewrites image references automatically.

The **operator itself** also needs to be mirrored — otherwise `helm install/upgrade`
will timeout waiting for the pod to pull from ghcr.io.

```bash
ECR=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com.cn

# Login
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} --profile ${AWS_PROFILE} | \
  docker login --username AWS --password-stdin ${ECR}

# Create ECR repos (nested paths supported)
for repo in openclaw/openclaw nginx astral-sh/uv otel/opentelemetry-collector openclaw-rocks/openclaw-operator; do
  aws ecr create-repository --repository-name "$repo" \
    --image-scanning-configuration scanOnPush=false \
    --region ${AWS_DEFAULT_REGION} --profile ${AWS_PROFILE} 2>/dev/null || true
done

# --- Agent images (rewritten by spec.registry) ---
docker pull ghcr.io/openclaw/openclaw:latest
docker tag  ghcr.io/openclaw/openclaw:latest          ${ECR}/openclaw/openclaw:latest
docker push ${ECR}/openclaw/openclaw:latest

docker pull nginx:1.27-alpine
docker tag  nginx:1.27-alpine                         ${ECR}/nginx:1.27-alpine
docker push ${ECR}/nginx:1.27-alpine

docker pull ghcr.io/astral-sh/uv:0.6-bookworm-slim
docker tag  ghcr.io/astral-sh/uv:0.6-bookworm-slim     ${ECR}/astral-sh/uv:0.6-bookworm-slim
docker push ${ECR}/astral-sh/uv:0.6-bookworm-slim

docker pull otel/opentelemetry-collector:0.120.0
docker tag  otel/opentelemetry-collector:0.120.0        ${ECR}/otel/opentelemetry-collector:0.120.0
docker push ${ECR}/otel/opentelemetry-collector:0.120.0

# --- Operator image (used by Helm via OPERATOR_IMAGE_REPO) ---
docker pull ghcr.io/openclaw-rocks/openclaw-operator:v0.26.2
docker tag  ghcr.io/openclaw-rocks/openclaw-operator:v0.26.2  ${ECR}/openclaw-rocks/openclaw-operator:v0.26.2
docker push ${ECR}/openclaw-rocks/openclaw-operator:v0.26.2
```

**Registry → ECR path mapping:**

| Upstream Image | CN ECR Repo |
|---|---|
| `ghcr.io/openclaw/openclaw:latest` | `${ECR}/openclaw/openclaw:latest` |
| `nginx:1.27-alpine` | `${ECR}/nginx:1.27-alpine` |
| `ghcr.io/astral-sh/uv:0.6-bookworm-slim` | `${ECR}/astral-sh/uv:0.6-bookworm-slim` |
| `otel/opentelemetry-collector:0.120.0` | `${ECR}/otel/opentelemetry-collector:0.120.0` |
| `ghcr.io/openclaw-rocks/openclaw-operator:v0.26.2` | `${ECR}/openclaw-rocks/openclaw-operator:v0.26.2` |

> **Note:** Agent images are rewritten by the operator's `spec.registry` field
> (set automatically by platform API when `AWS_PARTITION=aws-cn`).
> The operator's own image is overridden via `OPERATOR_IMAGE_REPO` in `.env` →
> `deploy.sh` passes `--set image.repository` to Helm.

### 5. Build & Push Platform Images

```bash
# Platform API
docker buildx build --platform linux/arm64 --no-cache \
  -t ${ECR}/openclaw-saas-platform:v$(cat platform/VERSION) --push platform/

# Metrics Exporter
docker buildx build --platform linux/arm64 --no-cache \
  -t ${ECR}/openclaw-saas-metrics-exporter:v$(cat platform/metrics-exporter/VERSION) --push platform/metrics-exporter/

# Billing Consumer
docker buildx build --platform linux/arm64 --no-cache \
  -t ${ECR}/openclaw-saas-billing-consumer:v$(cat platform/billing/VERSION) --push platform/billing/
```

### 6. Deploy Platform

```bash
cd infra
./scripts/deploy.sh --skip-cdk
```

`deploy.sh` handles: kubectl config → ALB Controller → OpenClaw Operator → K8s Secret → Platform API → DB migration → verification.

### 7. Verify

```bash
kubectl get pods -n openclaw-platform
kubectl port-forward -n openclaw-platform svc/platform-api 8000:80
curl http://localhost:8000/health
# {"status":"ok","version":"0.9.52"}
```

## Configuration

### `.env` — Single Source of Truth

All deployment configuration is centralized in `infra/.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_EMAIL` | ✅ | Admin account email |
| `ADMIN_PASSWORD` | ✅ | Admin account password |
| `JWT_SECRET` | ✅ | JWT signing secret (`openssl rand -hex 32`) |
| `AWS_REGION` | ✅ | `cn-northwest-1` |
| `AWS_PARTITION` | ✅ | `aws-cn` |
| `AWS_ACCOUNT_ID` | ✅ | `735091234506` |
| `METRICS_EXPORTER_REPO` | ✅ | `openclaw-saas-metrics-exporter` |
| `METRICS_EXPORTER_TAG` | ✅ | `v0.3.1` |
| `K8S_IN_CLUSTER` | | Default: `true` |
| `LOG_LEVEL` | | Default: `INFO` |
| `AVAILABLE_CHANNELS` | | Default: `feishu` |
| `DEFAULT_AGENT_IMAGE` | | CN custom image |
| `DEFAULT_AGENT_IMAGE_TAG` | | Default: `latest` |
| `OPERATOR_IMAGE_REPO` | | ECR repo path for operator image (CN: `openclaw-rocks/openclaw-operator`) |
| `OPERATOR_VERSION` | | Operator chart/image version (default: `0.26.2`) |

Auto-populated by `deploy.sh` from CDK outputs: `DATABASE_URL`, `SQS_QUEUE_URL`, `ECR_REGISTRY`.

### `cdk.json` — Infrastructure Parameters

Instance types, cluster size, domain — all in `cdk/cdk.json` context.

**CN-specific:** `aws_region: cn-northwest-1`, `"@aws-cdk/core:target-partitions": ["aws-cn"]`

## Components

### Platform API (`platform/`)

FastAPI backend + React web console. Manages tenants, agents, channels, billing.

### Metrics Exporter (`platform/metrics-exporter/`)

Sidecar that scrapes otel-collector Prometheus endpoint, computes usage deltas, pushes to SQS for billing.

**Data flow:** OpenClaw (diagnostics-otel plugin) → otel-collector `:9090/metrics` → metrics-exporter → SQS

### Billing Consumer (`platform/billing/`)

Consumes SQS usage events, aggregates into daily/monthly billing records.

### Agent Pod Architecture

Each agent runs as a StatefulSet with 4 containers:

| Container | Purpose |
|-----------|---------|
| `openclaw` | OpenClaw agent (Node.js, 3072MB heap) |
| `otel-collector` | OTLP → Prometheus metrics on `:9090` |
| `metrics-exporter` | Scrape otel-collector → SQS usage events |
| `gateway-proxy` | nginx reverse proxy for gateway |

**CN image mirroring:** The operator's `spec.registry` field rewrites all image
references to use CN ECR. See [Step 4](#4-mirror-upstream-images-to-cn-ecr).

### LLM Providers (CN)

| Provider | Auth | Notes |
|----------|------|-------|
| `openai-compatible` | API key + base URL | **CN default.** Any OpenAI-compatible endpoint |
| `bedrock-apikey` | `AWS_BEARER_TOKEN_BEDROCK` | Global Bedrock API key (cross-region) |
| `openai` | API key | |
| `anthropic` | API key | |

## Destroy & Redeploy

```bash
export AWS_PROFILE=cn AWS_DEFAULT_REGION=cn-northwest-1

# 1. Clean K8s resources first
kubectl delete openclawinstance --all --all-namespaces
kubectl delete ns openclaw-platform

# 2. CDK destroy (reverse order)
cd infra/cdk
cdk destroy openclaw-saas-rds openclaw-saas-iam --force
# Empty S3 bucket first:
BUCKET=$(aws s3 ls | grep openclaw-saas-backups | awk '{print $3}')
aws s3 rm s3://${BUCKET} --recursive
cdk destroy openclaw-saas-s3 --force
cdk destroy openclaw-saas-eks --force    # ~15-20 min
# ECR repos with images need manual deletion:
for repo in openclaw-saas-platform openclaw-saas-billing-consumer openclaw-saas-metrics-exporter; do
  aws ecr delete-repository --repository-name ${repo} --force --region ${AWS_DEFAULT_REGION}
done
cdk destroy openclaw-saas-ecr --force
cdk destroy openclaw-saas-sqs --force
cdk destroy openclaw-saas-vpc --force
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| CDK deploys to wrong region | CDK CLI uses default profile region | Set `aws_region` in `cdk.json` context |
| `kubectl: Unauthorized` | CDK cluster needs role assumption | Add `--role-arn` to `update-kubeconfig` |
| `sts:AssumeRole AccessDenied` | IAM user lacks permission | Add inline policy for `sts:AssumeRole` on `openclaw-saas-eks-*` |
| ECR stack `AlreadyExists` | Repos survive stack deletion | `aws ecr delete-repository --force` first |
| S3 stack `BucketNotEmpty` | Bucket has data | `aws s3 rm --recursive` first |
| EKS deletion 30+ min | Lambda VPC ENI cleanup | Wait, or manually detach ENIs |
| metrics-exporter CrashLoop | Port 9090 conflict with otel-collector | Fixed in v0.3.0+ (no Prometheus server) |
| No usage metrics | OpenClaw not sending OTEL data | Fixed in v0.9.52 (diagnostics-otel plugin) |

## Branch Workflow

```
main (Global) → cn (China) → cn-workshop
```

Generic fixes: cherry-pick `main → cn`. CN-specific stays on `cn`. Never reverse-merge.

## Versioning

| Component | File | Current |
|-----------|------|---------|
| Platform API | `platform/VERSION` | 0.9.52 |
| Metrics Exporter | `platform/metrics-exporter/VERSION` | 0.3.1 |
| Billing Consumer | `platform/billing/VERSION` | 0.1.0 |
| Operator | Helm chart | 0.26.2 |

Bump the VERSION file → build image → update `.env` tag → `deploy.sh`.
