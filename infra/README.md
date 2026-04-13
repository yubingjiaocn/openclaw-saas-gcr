# OpenClaw SaaS Infrastructure — China Region

AWS CDK stacks + Kubernetes manifests + deployment automation for OpenClaw SaaS on EKS (cn-northwest-1).

## Directory Structure

| Directory | Description |
|-----------|-------------|
| `cdk/` | CDK stacks: VPC, EKS, RDS, S3, SQS, ECR, IAM |
| `k8s/platform/` | Kubernetes manifests (deployment, service, rbac) |
| `scripts/deploy.sh` | Automated deployment script |
| `.env.cn` | China (cn-northwest-1) environment template |
| `.env.global` | Global (us-west-2) environment template |
| `.env.example` | Generic template with docs |

## Configuration

### `.env` — Single Source of Truth

All deployment config lives in `.env`. No hardcoded defaults in `deploy.sh`.

```bash
# Pick environment:
cp .env.cn .env

# Fill credentials:
vim .env    # Set ADMIN_PASSWORD, JWT_SECRET
```

See `.env.example` for full variable reference.

### `cdk.json` — Infrastructure Parameters

Instance types, cluster size, region — all in `cdk/cdk.json` context.

**CN-specific:** `aws_region: cn-northwest-1`, `target-partitions: ["aws-cn"]`

## Deploy

### Prerequisites

- AWS CLI configured (`~/.aws/config` with `[profile cn]`)
- CDK CLI, kubectl, helm, jq, Docker with buildx
- IAM user with `sts:AssumeRole` on `openclaw-saas-eks-*` roles

### Full Deploy

```bash
export AWS_PROFILE=cn
export AWS_DEFAULT_REGION=cn-northwest-1

# 1. Configure
cd infra && cp .env.cn .env && vim .env

# 2. CDK
cd cdk && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cdk bootstrap aws://${AWS_ACCOUNT_ID}/${AWS_DEFAULT_REGION}
cdk deploy openclaw-saas-vpc --require-approval never
cdk deploy openclaw-saas-ecr openclaw-saas-sqs openclaw-saas-s3 --require-approval never --concurrency 3
cdk deploy openclaw-saas-eks --require-approval never                    # ~15 min
cdk deploy openclaw-saas-iam openclaw-saas-rds --require-approval never --concurrency 2
cd ..

# 3. Build & push images (see root README)

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
| eks | EKS cluster, 2× Graviton t4g.medium | 15 min |
| iam | IRSA roles, node policies | 1 min |
| rds | PostgreSQL t4g.micro | 5 min |

## deploy.sh Flow

```
main()
  ├── Load .env
  ├── check_prerequisites
  ├── deploy_cdk (unless --skip-cdk)
  ├── configure_kubectl (with --role-arn for CDK-created cluster)
  ├── install_alb_controller
  ├── install_openclaw_operator
  ├── create_platform_secret ← reads .env + CDK outputs → K8s Secret
  ├── deploy_platform_api
  ├── run_db_migration
  └── verify_deployment
```

## Destroy

```bash
export AWS_PROFILE=cn AWS_DEFAULT_REGION=cn-northwest-1

# 1. Clean K8s resources first
kubectl delete openclawinstance --all --all-namespaces
kubectl delete ns openclaw-platform

# 2. CDK destroy (reverse order)
cd cdk
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

**Note:** ECR repos with images and S3 buckets with data survive `cdk destroy`. Delete manually first.

## Cost Estimate (CN)

~$150-200/month:

| Resource | Monthly Cost |
|----------|-------------|
| EKS control plane | ~$73 |
| 2× t4g.medium nodes | ~$30 |
| RDS t4g.micro | ~$13 |
| NAT Gateway | ~$32 |
| Other (S3, SQS, VPC endpoints) | ~$20 |
