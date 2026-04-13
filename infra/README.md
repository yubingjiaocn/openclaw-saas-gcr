# OpenClaw SaaS Infrastructure

AWS CDK stacks + Kubernetes manifests + deployment automation for OpenClaw SaaS on EKS.

## Directory Structure

| Directory | Description |
|-----------|-------------|
| `cdk/` | CDK stacks: VPC, EKS, RDS, S3, SQS, ECR, IAM, CloudFront |
| `k8s/platform/` | Kubernetes manifests (deployment, service, ingress, rbac) |
| `scripts/deploy.sh` | Automated deployment script |
| `.env.global` | Global (us-west-2) environment template |
| `.env.cn` | China (cn-northwest-1) environment template |
| `.env.example` | Generic template with docs |
| `docs/` | Runbook, architecture diagrams |

## Configuration

### `.env` — Single Source of Truth

All deployment config lives in `.env`. No hardcoded defaults in `deploy.sh` or `config.py`.

```bash
# Pick environment:
cp .env.global .env   # Global
cp .env.cn .env       # China

# Fill credentials:
vim .env
```

See `.env.example` for full variable reference.

### `cdk.json` — Infrastructure Parameters

Instance types, cluster size, domain, SSL cert — all in `cdk/cdk.json` context.

## Deploy

### Prerequisites

- AWS CLI, CDK CLI, kubectl, helm, jq, Docker with buildx
- IAM user with `sts:AssumeRole` on `openclaw-saas-eks-*` roles

### Full Deploy

```bash
# 1. Configure
cp .env.global .env && vim .env

# 2. CDK
cd cdk && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cdk deploy openclaw-saas-vpc --require-approval never
cdk deploy openclaw-saas-ecr openclaw-saas-sqs openclaw-saas-s3 --require-approval never --concurrency 3
cdk deploy openclaw-saas-eks --require-approval never
cdk deploy openclaw-saas-iam openclaw-saas-rds --require-approval never --concurrency 2
cd ..

# 3. Build & push images (see root README for commands)

# 4. Deploy K8s
./scripts/deploy.sh --skip-cdk
```

### Update Platform Only

```bash
./scripts/deploy.sh --skip-cdk
```

### CDK Stacks

| Stack | Resources | ~Deploy Time |
|-------|-----------|-------------|
| vpc | VPC, Subnets, NAT, Endpoints | 3 min |
| ecr | 3 container repos | 30s |
| sqs | Usage events queue + DLQ | 30s |
| s3 | Backups bucket | 30s |
| eks | EKS cluster, Graviton nodes | 15 min |
| iam | IRSA roles, node policies | 1 min |
| rds | PostgreSQL t4g.micro | 5 min |
| cloudfront | CloudFront distribution (Global only) | 5 min |

## deploy.sh Flow

```
main()
  ├── Load .env
  ├── check_prerequisites
  ├── deploy_cdk (unless --skip-cdk)
  ├── configure_kubectl
  ├── install_alb_controller
  ├── install_openclaw_operator
  ├── create_platform_secret ← reads .env + CDK outputs → K8s Secret
  ├── deploy_platform_api
  ├── update_cloudfront_origin
  ├── run_db_migration
  └── verify_deployment
```

## Destroy

```bash
# 1. Clean K8s resources first
kubectl delete openclawinstance --all --all-namespaces
kubectl delete ns openclaw-platform

# 2. CDK destroy (reverse order)
cd cdk
cdk destroy openclaw-saas-rds openclaw-saas-iam --force
# Empty S3 bucket first:
aws s3 rm s3://openclaw-saas-backups-*-* --recursive
cdk destroy openclaw-saas-s3 --force
cdk destroy openclaw-saas-eks --force   # ~15-20 min
cdk destroy openclaw-saas-sqs openclaw-saas-ecr --force
cdk destroy openclaw-saas-vpc --force
```

**Note:** ECR repos with images need `aws ecr delete-repository --force` before stack deletion.
