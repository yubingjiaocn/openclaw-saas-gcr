# OpenClaw SaaS on EKS — China Region (cn branch)

Multi-tenant OpenClaw SaaS platform for **AWS China Region** (cn-northwest-1, Ningxia).

> This is the `cn` branch. For Global region (us-west-2), see the [`main`](https://github.com/duchenxi/openclaw-saas-platform/tree/main) branch.

## Architecture

Same core architecture as Global — EKS + RDS + SQS + per-tenant namespace isolation — with China-specific adaptations:

| | Global (`main`) | China (`cn`) |
|---|---|---|
| **Region** | us-west-2 | cn-northwest-1 |
| **Account** | 956045422469 | 735091234506 |
| **ARN prefix** | `arn:aws` | `arn:aws-cn` |
| **STS / ECR domains** | `.amazonaws.com` | `.amazonaws.com.cn` |
| **Bedrock** | Available (default LLM) | Not available |
| **Default LLM provider** | bedrock-apikey | openai-compatible |
| **Agent image** | Upstream `ghcr.io/openclaw/openclaw` | Custom image with pre-installed tools |
| **Channels** | All (Slack, Teams, etc.) | Feishu |

### Custom Image (`custom-image/`)

China's firewall blocks runtime `npx` downloads, so the CN branch builds a custom agent image that pre-installs all required tools:

```
custom-image/
├── Dockerfile              # Based on public.ecr.aws openclaw image (arm64)
└── kiro-agent-config.json  # Default Kiro agent configuration
```

**Pre-installed tools:**
- **acpx** — Agent Collaboration Protocol extension (pinned to base image version)
- **claude-agent-acp** — Claude agent binary (`@zed-industries/claude-agent-acp`)
- **kiro-cli** — Kiro CLI (native aarch64 binary, headless mode)
- **jq** — JSON processor

The image is hosted on Public ECR (`public.ecr.aws/i4x4j7g8/openclaw-saas/`) which is accessible from China.

### Key Code Differences from `main`

- **`platform/api/models/agent.py`** — `bedrock-irsa` provider removed (Bedrock unavailable)
- **`platform/api/services/k8s_client.py`** — ACP agents pre-installed in image (no init container, no runtime npx); Kiro config copied from image layer to PVC for session persistence
- **`platform/web-console/src/App.jsx`** — Default provider: `openai-compatible`
- **`platform/api/config.py`** — Defaults: `cn-northwest-1`, `aws-cn` partition, `feishu` channel

## Repository Structure

```
platform/           Management API + Web Console + Billing + Metrics Exporter
  ├── api/          FastAPI backend (tenant/agent CRUD, K8s client)
  ├── web-console/  React frontend (admin console)
  ├── billing/      SQS consumer + usage aggregator
  └── metrics-exporter/  Sidecar for agent pods (Prometheus → SQS)

custom-image/       CN-specific OpenClaw agent image (pre-installed tools)

infra/              Infrastructure as Code + K8s manifests
  ├── cdk/          AWS CDK stacks (VPC, EKS, RDS, SQS, ECR, IAM)
  ├── k8s-platform/ K8s manifests for platform components
  ├── scripts/      Deployment scripts
  └── observability/ Prometheus, Grafana, Loki

contracts/          Shared contracts: API specs, CRD conventions, event schemas
```

## Deploy

### Prerequisites

- AWS CLI configured for China region (`--profile cn --region cn-northwest-1`)
- `kubectl`, `helm`, `aws-cdk` installed
- Docker (buildx for arm64)

### Infrastructure

```bash
export AWS_PROFILE=cn
export CDK_DEFAULT_ACCOUNT=735091234506
export CDK_DEFAULT_REGION=cn-northwest-1

cd infra/cdk
cdk deploy --all
```

### Platform

```bash
# Configure kubectl for CN EKS cluster
aws eks update-kubeconfig --name openclaw-saas-dev-cluster \
  --region cn-northwest-1 --profile cn

# Deploy K8s components
cd infra && ./scripts/deploy.sh --skip-cdk
```

### Custom Image

```bash
cd custom-image

# Build for arm64 (Graviton)
docker buildx build --platform linux/arm64 -t openclaw-custom-cn:latest .

# Push to Public ECR (us-east-1, accessible from China)
aws ecr-public get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin public.ecr.aws
docker tag openclaw-custom-cn:latest \
  public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom-cn:latest
docker push public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom-cn:latest
```

Set the image in platform config:
```
DEFAULT_AGENT_IMAGE=public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom-cn
DEFAULT_AGENT_IMAGE_TAG=latest
```

## Branch Workflow

```
main (Global, us-west-2)
  └── cn (China, cn-northwest-1)    ← this branch
       └── cn-workshop (workshop environments)
```

- **`main`** → develop and validate features on Global first
- **`cn`** → adapt for China (LLM providers, custom image, AWS partition)
- **`cn-workshop`** → workshop-specific deployment scripts on top of `cn`

Flow is one-directional: `main → cn → cn-workshop`. Never reverse-merge.

## License

[MIT License](LICENSE)
