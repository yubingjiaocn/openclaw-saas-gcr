# OpenClaw SaaS on EKS

Multi-tenant OpenClaw SaaS platform on AWS EKS. Supports Global (us-west-2) and China (cn-northwest-1) regions.

## Architecture

```
                    Internet
                       │
                  CloudFront (Global) / NLB (CN)
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
| **Default LLM** | bedrock-irsa (no API key needed) | openai-compatible |
| **Agent Image** | Upstream openclaw (operator default) | Custom (pre-installed tools) |
| **Channels** | All | Feishu |
| **Ingress** | NLB + CloudFront | NLB |

## Quick Start

### 1. Configure Environment

```bash
cd infra

# Pick your environment template:
cp .env.global .env   # Global (us-west-2)
# or
cp .env.cn .env       # China (cn-northwest-1)

# Fill in required credentials:
vim .env              # Set ADMIN_PASSWORD, JWT_SECRET
```

All deployment config lives in `.env`. No hardcoded values elsewhere.

### 2. Deploy Infrastructure (CDK)

```bash
cd infra/cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap (first time only)
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>

# Deploy stacks (step by step to avoid OOM):
cdk deploy openclaw-saas-vpc --require-approval never
cdk deploy openclaw-saas-ecr openclaw-saas-sqs openclaw-saas-s3 --require-approval never --concurrency 3
cdk deploy openclaw-saas-eks --require-approval never                    # ~15 min
cdk deploy openclaw-saas-iam openclaw-saas-rds --require-approval never --concurrency 2
```

**CDK Stacks:** vpc, ecr, sqs, s3, eks (K8s 1.30, Graviton), iam, rds (PostgreSQL), cloudfront (Global only)

### 3. Build & Push Images

```bash
ECR=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
aws ecr get-login-password --region <REGION> | docker login --username AWS --password-stdin $ECR

# Platform API
docker buildx build --platform linux/arm64 \
  -t $ECR/openclaw-saas-platform:v$(cat platform/VERSION) --push platform/

# Metrics Exporter
docker buildx build --platform linux/arm64 \
  -t $ECR/openclaw-saas-metrics-exporter:v$(cat platform/metrics-exporter/VERSION) --push platform/metrics-exporter/

# Billing Consumer
docker buildx build --platform linux/arm64 \
  -t $ECR/openclaw-saas-billing-consumer:v$(cat platform/billing/VERSION) --push platform/billing/
```

### 4. Deploy Platform

```bash
cd infra
./scripts/deploy.sh
# or skip CDK if already deployed:
./scripts/deploy.sh --skip-cdk
```

`deploy.sh` handles: kubectl config → ALB Controller → OpenClaw Operator → K8s Secret → Platform API → CloudFront → DB migration → verification.

### 5. Verify

```bash
kubectl get pods -n openclaw-platform
curl https://openclaw.chenxqdu.space/health   # Global
# or
kubectl port-forward -n openclaw-platform svc/platform-api 8000:80
curl http://localhost:8000/health
# {"status":"ok","version":"0.9.55"}
```

## Configuration

### Single Source of Truth: `.env`

All deployment configuration is centralized in `infra/.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_EMAIL` | ✅ | Admin account email |
| `ADMIN_PASSWORD` | ✅ | Admin account password |
| `JWT_SECRET` | ✅ | JWT signing secret (`openssl rand -hex 32`) |
| `AWS_REGION` | ✅ | Target AWS region |
| `AWS_PARTITION` | ✅ | `aws` or `aws-cn` |
| `AWS_ACCOUNT_ID` | ✅ | AWS account ID |
| `METRICS_EXPORTER_REPO` | ✅ | ECR repo name for metrics-exporter |
| `METRICS_EXPORTER_TAG` | ✅ | metrics-exporter image tag |
| `K8S_IN_CLUSTER` | | Default: `true` |
| `LOG_LEVEL` | | Default: `INFO` |
| `AVAILABLE_CHANNELS` | | Empty = all, or comma-separated |
| `DEFAULT_AGENT_IMAGE` | | Empty = operator default |
| `DEFAULT_AGENT_IMAGE_TAG` | | Default: `latest` |
| `PLATFORM_VERSION` | | Platform API version tag |

Auto-populated by `deploy.sh` from CDK outputs: `DATABASE_URL`, `SQS_QUEUE_URL`, `ECR_REGISTRY`.

### CDK Context (`cdk.json`)

Infrastructure-level settings (instance types, cluster size, domain) are in `infra/cdk/cdk.json`.

## Components

### Platform API (`platform/`)

FastAPI backend + React web console. Manages tenants, agents, channels, billing.

- **Version:** v0.9.55
- **Image:** `openclaw-saas-platform:v0.9.55`

### Metrics Exporter (`platform/metrics-exporter/`)

Sidecar that scrapes otel-collector Prometheus endpoint, computes usage deltas, pushes to SQS for billing.

- **Version:** v0.3.0
- **Image:** `openclaw-saas-metrics-exporter:v0.3.0`
- **Data flow:** otel-collector `:9090/metrics` → delta computation → SQS

### Billing Consumer (`platform/billing/`)

Consumes SQS usage events, aggregates into daily/monthly billing records.

- **Version:** v0.1.0
- **Image:** `openclaw-saas-billing-consumer:v0.1.0`

### OpenClaw Operator

Manages OpenClawInstance CRDs → StatefulSets with sidecars.

- **Version:** v0.26.2 (Helm chart `openclaw-operator-0.26.2`)
- **Source:** `oci://ghcr.io/openclaw-rocks/charts/openclaw-operator`

### Agent Pod Architecture

Each agent runs as a StatefulSet with 4 containers:

| Container | Purpose |
|-----------|---------|
| `openclaw` | OpenClaw agent (Node.js, 3072MB heap) |
| `otel-collector` | OTLP → Prometheus metrics on `:9090` |
| `metrics-exporter` | Scrape otel-collector → SQS usage events |
| `gateway-proxy` | nginx reverse proxy for gateway |

### LLM Providers

| Provider | Auth | Notes |
|----------|------|-------|
| `bedrock-irsa` | Platform-managed (no key needed) | **Global default.** Node role → Bedrock |
| `bedrock-apikey` | AWS Access Key + Secret | Manual IAM credentials |
| `openai` | API key | |
| `anthropic` | API key | |
| `openai-compatible` | API key + base URL | **CN default.** Any OpenAI-compatible endpoint |

## Branch Workflow

```
main (Global) → cn (China) → cn-workshop
```

- **main:** Global production (us-west-2). Upstream OpenClaw images.
- **cn:** China production (cn-northwest-1). Custom images with pre-installed tools.
- **cn-workshop:** Training/demo. Static manifests + deployment scripts.

See `BRANCHES.md` for full diff matrix.

Generic fixes: cherry-pick `main → cn`. CN-specific stays on `cn`. Never reverse-merge.

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| metrics-exporter CrashLoop | Port 9090 conflict with otel-collector | Fixed in v0.3.0 (no Prometheus server) |
| `No API key for amazon-bedrock` | OpenClaw needs env vars, not IMDS | bedrock-irsa injects temp credentials |
| CDK deploys to wrong region | CDK CLI ignores `--profile` region | Set `aws_region` in `cdk.json` context |
| `kubectl: Unauthorized` | CDK cluster needs role assumption | `--role-arn` in `update-kubeconfig` |
| ECR stack `AlreadyExists` | Repos survive stack deletion | `aws ecr delete-repository --force` |
| S3 stack `BucketNotEmpty` | Bucket has data | `aws s3 rm --recursive` first |
| EKS deletion 30+ min | Lambda VPC ENI cleanup | Wait, or manually detach ENIs |

## Versioning

| Component | File | Current |
|-----------|------|---------|
| Platform API | `platform/VERSION` | 0.9.55 |
| Metrics Exporter | `platform/metrics-exporter/VERSION` | 0.3.0 |
| Billing Consumer | `platform/billing/VERSION` | 0.1.0 |
| Operator | Helm chart | 0.26.2 |

Bump the VERSION file → build image → update `.env` tag → `deploy.sh`.
