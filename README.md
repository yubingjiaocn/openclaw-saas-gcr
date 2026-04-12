# OpenClaw SaaS on Amazon EKS

Multi-tenant OpenClaw SaaS platform running on Amazon EKS in **us-west-2** (Oregon).

> **Other regions**: This is the main branch for Global region deployment. For China region deployments, see the `cn` and `cn-workshop` branches.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Account                              │
│                       956045422469 (us-west-2)                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ VPC (2 AZs, Private/Public Subnets, NAT Gateway)           │ │
│  │                                                              │ │
│  │  ┌─────────────────────────────────────────────────────┐   │ │
│  │  │ EKS Cluster (K8s 1.30)                             │   │ │
│  │  │  • Graviton nodes (ARM64, t4g.medium)              │   │ │
│  │  │  • AWS Load Balancer Controller (NLB)               │   │ │
│  │  │  • openclaw-operator (manages OpenClawInstance)    │   │ │
│  │  │                                                      │   │ │
│  │  │  ┌─────────────────────────────────────────────┐   │   │ │
│  │  │  │ openclaw-platform namespace                │   │   │ │
│  │  │  │  • platform-api (FastAPI)                  │   │   │ │
│  │  │  │  • web-console (React frontend)            │   │   │ │
│  │  │  └─────────────────────────────────────────────┘   │   │ │
│  │  │                                                      │   │ │
│  │  │  ┌─────────────────────────────────────────────┐   │   │ │
│  │  │  │ tenant-{name} namespaces (isolated)        │   │   │ │
│  │  │  │  • OpenClawInstance CRDs                   │   │   │ │
│  │  │  │  • StatefulSets (agent pods)               │   │   │ │
│  │  │  │  • PVCs, NetworkPolicy, ResourceQuota      │   │   │ │
│  │  │  └─────────────────────────────────────────────┘   │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     RDS      │  │     SQS      │  │     ECR      │          │
│  │ PostgreSQL16 │  │ (usage queue)│  │  (3 repos)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└───────────────────────────────────────────────────────────────────┘
```

**Core Features:**
- Multi-tenant SaaS with per-tenant namespace isolation
- K8s Operator for declarative OpenClaw instance lifecycle
- Usage-based billing pipeline (Prometheus → SQS → aggregator)
- Web console for tenant/agent management
- ResourceQuota + NetworkPolicy + LimitRange per tenant
- IRSA for AWS service access (SQS, ECR, CloudWatch)

## Repository Structure

```
platform/         Management API, Web Console, Billing, Metrics Exporter
  ├── api/        FastAPI backend (tenant/agent CRUD, K8s client)
  ├── web-console/ React frontend (admin console)
  ├── billing/    SQS consumer + usage aggregator
  └── metrics-exporter/ Sidecar for agent pods (Prometheus + SQS)

infra/            Infrastructure as Code + K8s manifests
  ├── cdk/        AWS CDK stacks (VPC, EKS, RDS, SQS, ECR, IAM)
  ├── k8s-platform/ K8s manifests for platform components
  ├── scripts/    Automated deployment scripts
  ├── observability/ Prometheus, Grafana, Loki
  └── cicd/       GitHub Actions workflows

contracts/        Shared conventions and schemas
  ├── crd-conventions.md CRD labels, naming, metrics standards
  ├── api-specs/  OpenAPI specifications
  └── event-schemas/ SQS event JSON schemas
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Container Orchestration** | Kubernetes 1.30 (Amazon EKS) |
| **Compute** | Graviton (ARM64) nodes |
| **Backend** | Python FastAPI + asyncio |
| **Frontend** | React (Vite) |
| **Database** | PostgreSQL 16 (RDS) |
| **Queue** | Amazon SQS |
| **Storage** | EBS (K8s PVCs), S3 (backups) |
| **Observability** | Prometheus, Grafana, Loki |
| **IaC** | AWS CDK (Python) |
| **Operator** | openclaw-operator (Helm chart) |

## Quick Start

### Prerequisites

- AWS CLI configured for account `956045422469`
- `kubectl`, `helm`, `aws-cdk` installed
- Docker for building platform image

### Deploy Infrastructure

```bash
# 1. Bootstrap CDK (first time only)
cd infra/cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export CDK_DEFAULT_ACCOUNT=956045422469
export CDK_DEFAULT_REGION=us-west-2
cdk bootstrap

# 2. Deploy all stacks
cdk deploy --all --require-approval never
```

### Deploy Platform

```bash
# 3. Configure kubectl
CLUSTER_NAME=$(aws cloudformation describe-stacks \
  --stack-name openclaw-saas-dev-eks \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterName'].OutputValue" \
  --output text)
aws eks update-kubeconfig --name ${CLUSTER_NAME} --region us-west-2

# 4. Install K8s components
cd ../../infra
./scripts/deploy.sh --skip-cdk

# 5. Access platform (NLB — restricted to CloudFront IPs only)
kubectl get svc platform-api -n openclaw-platform
# NLB DNS is only reachable via CloudFront (prefix list pl-82a045eb)
# Direct curl will timeout — use CloudFront distribution to access
```

### Local Development

```bash
# Platform API (local)
cd platform/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn api.main:app --reload

# Web Console (local)
cd platform/web-console
npm install
npm run dev
```

## Deployment

### Production Image Build

```bash
# Build and push platform image
cd platform
docker build -t openclaw-saas-platform:latest .

ECR_REPO=956045422469.dkr.ecr.us-west-2.amazonaws.com/openclaw-saas-platform
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin ${ECR_REPO}

docker tag openclaw-saas-platform:latest ${ECR_REPO}:latest
docker push ${ECR_REPO}:latest
```

### Update Platform Deployment

```bash
kubectl rollout restart deployment/platform-api -n openclaw-platform
kubectl rollout status deployment/platform-api -n openclaw-platform
```

## Key Components

### Platform API
Management API for tenant/agent lifecycle, deployed to `openclaw-platform` namespace.

**Endpoints:**
- `POST /api/v1/tenants` - Create tenant (namespace + RBAC + quotas)
- `POST /api/v1/tenants/{id}/agents` - Create agent (OpenClawInstance CRD)
- `GET /api/v1/tenants/{id}/agents/{agent_id}/logs` - Stream pod logs
- `GET /api/v1/usage` - Query billing/usage metrics

**Configuration:** Secret `platform-api-config` with DATABASE_URL, SQS_QUEUE_URL, AWS_REGION, ECR_REGISTRY

### Metrics Exporter
Sidecar container injected into each agent pod. Scans `~/.openclaw/usage/*.json` files and pushes events to SQS.

**Environment:** TENANT_NAME, AGENT_NAME, SQS_QUEUE_URL, AWS_DEFAULT_REGION

### Billing Consumer
Standalone deployment that consumes SQS usage events and aggregates into `usage_events` table.

**Environment:** SQS_QUEUE_URL, DATABASE_URL, AWS_DEFAULT_REGION

### Web Console
React SPA served via platform-api at `/` (static files). Provides admin UI for tenant/agent management.

**Build:** `npm run build` → `platform/web-console/dist/`

## Configuration

All platform configuration is managed via K8s Secret `platform-api-config`:

| Key | Description | Default (main) |
|-----|-------------|----------------|
| `AWS_REGION` | AWS region | `us-west-2` |
| `AWS_PARTITION` | AWS partition | `aws` |
| `AWS_ACCOUNT_ID` | AWS account ID | `956045422469` |
| `ECR_REGISTRY` | ECR domain | `956045422469.dkr.ecr.us-west-2.amazonaws.com` |
| `SQS_QUEUE_URL` | Usage events queue | (from CDK output) |
| `DATABASE_URL` | PostgreSQL connection string | (from CDK output) |
| `AVAILABLE_CHANNELS` | Message channels (empty = all) | `` (all enabled) |
| `DEFAULT_AGENT_IMAGE` | Custom agent image (empty = use operator default) | `` (use ghcr.io/openclaw/openclaw) |

## Operations

### Scale EKS Nodes

```bash
aws eks update-nodegroup-config \
  --cluster-name ${CLUSTER_NAME} \
  --nodegroup-name GravitonNodes \
  --scaling-config minSize=2,maxSize=10,desiredSize=5
```

### View Logs

```bash
# Platform API logs
kubectl logs -n openclaw-platform -l app=platform-api -f

# Specific agent logs
kubectl logs -n tenant-{name} pod/{agent-name}-0 -c openclaw -f

# Metrics exporter logs
kubectl logs -n tenant-{name} pod/{agent-name}-0 -c metrics-exporter -f
```

### Database Access

```bash
# Get DB credentials
DB_SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name openclaw-saas-dev-rds \
  --query "Stacks[0].Outputs[?OutputKey=='DbSecretArn'].OutputValue" \
  --output text)

aws secretsmanager get-secret-value --secret-id ${DB_SECRET_ARN} \
  --query SecretString --output text | jq

# Port-forward via psql
kubectl run psql-client --rm -it --image=postgres:16-alpine -- \
  psql "postgresql://<user>:<pass>@<endpoint>:5432/openclawsaas"
```

### Monitoring

```bash
# Check agent metrics
kubectl port-forward -n tenant-{name} pod/{agent-name}-0 9090:9090
curl http://localhost:9090/metrics

# SQS queue depth
aws cloudwatch get-metric-statistics \
  --namespace AWS/SQS \
  --metric-name ApproximateNumberOfMessagesVisible \
  --dimensions Name=QueueName,Value=openclaw-saas-usage-events \
  --statistics Average \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300
```

## Documentation

- [Infrastructure README](infra/README.md) - CDK deployment details
- [Platform README](platform/README.md) - Platform components overview
- [CRD Conventions](contracts/crd-conventions.md) - Namespace, labels, metrics standards
- [Access Agent Web UI](platform/docs/access-agent-webui.md) - Port-forward guide for OpenClaw Control UI
- [Chromium Sidecar](platform/docs/chromium-sidecar.md) - Browser automation sidecar configuration
- [BRANCHES.md](BRANCHES.md) - Branch workflow and cross-region differences
- [VERSIONS.md](VERSIONS.md) - Version tracking and image tags

## Multi-Region Deployment

This repository supports multiple AWS regions/partitions via branch strategy:

- **`main`** (this branch) - Global region (us-west-2), account 956045422469
- **`cn`** - China region (cn-northwest-1), account 735091234506, adapted for China-specific requirements
- **`cn-workshop`** - China workshop environment with quickstart scripts and pre-built images

See [BRANCHES.md](BRANCHES.md) for detailed differences and development workflow.

## Cost Estimate (us-west-2)

Typical monthly cost for dev/test deployment:

- EKS control plane: ~$73/month
- EC2 nodes (2× t4g.medium): ~$30/month
- RDS (db.t4g.micro): ~$13/month
- NAT Gateway: ~$32/month
- NLB + S3 + ECR + CloudWatch: ~$20/month
- **Total: ~$170/month**

For production HA: add Multi-AZ RDS (+$13), extra NAT gateways (+$32/AZ), reserved instances (−30%).

## License

[MIT License](LICENSE)

## Production Endpoint

- **Domain**: https://openclaw.chenxqdu.space
- **Admin**: chenxqdu@amazon.com
- **GitHub**: duchenxi/openclaw-saas-platform (main branch)
