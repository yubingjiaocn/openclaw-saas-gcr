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
| **Service** | NLB + CloudFront | LoadBalancer (NLB) |
| **ECR** | Private (us-west-2) | **Private (cn-northwest-1)** |

## Deploy

### Prerequisites

- AWS CLI configured (`~/.aws/config` with `[profile cn]` region=cn-northwest-1)
- `kubectl`, `helm`, `aws-cdk`, `jq`, Docker with buildx
- IAM user needs `sts:AssumeRole` permission for `openclaw-saas-eks-*` roles

### 1. Configuration

```bash
cd infra && cp .env.example .env
# Fill ADMIN_EMAIL, ADMIN_PASSWORD, JWT_SECRET (required)
```

### 2. CDK Infrastructure

> **⚠️ Critical:** Always set `AWS_DEFAULT_REGION` explicitly. CDK CLI uses the default AWS profile's region, not `--profile`'s region, when setting `CDK_DEFAULT_REGION` for the app. The `aws_region` context in `cdk.json` is the reliable override.

```bash
export AWS_PROFILE=cn
export AWS_DEFAULT_REGION=cn-northwest-1
export CDK_DEFAULT_ACCOUNT=735091234506
export CDK_DEFAULT_REGION=cn-northwest-1

cd infra/cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap aws://735091234506/cn-northwest-1

# Deploy step by step (recommended over --all to avoid OOM):
cdk deploy openclaw-saas-vpc --require-approval never
cdk deploy openclaw-saas-ecr openclaw-saas-sqs openclaw-saas-s3 --require-approval never --concurrency 3
cdk deploy openclaw-saas-eks --require-approval never   # ~15 min
cdk deploy openclaw-saas-iam openclaw-saas-rds --require-approval never --concurrency 2
```

**CDK Stacks:** vpc, ecr, sqs, s3, eks (K8s 1.30, 2× Graviton t4g.medium), iam, rds (PostgreSQL t4g.micro)

### 3. EKS Access Setup

CDK creates the EKS cluster with a Lambda-managed IAM role. Your IAM user needs to assume that role:

```bash
# Get the creation role ARN
CREATION_ROLE=$(aws cloudformation describe-stacks --stack-name openclaw-saas-eks \
  --region cn-northwest-1 --profile cn \
  --query 'Stacks[0].Outputs[?OutputKey==`KubectlRoleArn`].OutputValue' --output text)

# Grant your user permission to assume the role
aws iam put-user-policy --user-name YOUR_USER \
  --policy-name AssumeEKSCreationRole \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws-cn:iam::735091234506:role/openclaw-saas-eks-*"
    }]
  }' --profile cn --region cn-northwest-1

# Add your user to the creation role trust policy
# (update-assume-role-policy to add your user ARN to the trust policy)

# Configure kubectl with the role
aws eks update-kubeconfig --name openclaw-saas-cluster \
  --region cn-northwest-1 --profile cn --role-arn "$CREATION_ROLE"

# Verify
kubectl get nodes
```

### 4. Build & Push Images

> **⚠️ CN branch → Private ECR only.** Public ECR is only for cn-workshop.

```bash
aws ecr get-login-password --region cn-northwest-1 --profile cn | \
  docker login --username AWS --password-stdin 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn

docker buildx build --platform linux/arm64 --no-cache \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-platform:v$(cat platform/VERSION) \
  --push platform/

docker buildx build --platform linux/arm64 --no-cache \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-metrics-exporter:v$(cat platform/metrics-exporter/VERSION) \
  --push platform/metrics-exporter/

docker buildx build --platform linux/arm64 --no-cache \
  -t 735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-billing-consumer:v$(cat platform/billing/VERSION) \
  --push platform/billing/
```

### 5. Platform Deployment

```bash
cd infra
export AWS_PROFILE=cn AWS_DEFAULT_REGION=cn-northwest-1

# Option A: Use deploy.sh (skip CDK if already done)
./scripts/deploy.sh --skip-cdk --platform-version v0.9.50

# Option B: Manual deployment (more control)
export PLATFORM_IMAGE="735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw-saas-platform:v0.9.50"

# Install ALB Controller
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=openclaw-saas-cluster \
  --set serviceAccount.create=true \
  --set region=cn-northwest-1 \
  --set vpcId=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=*OpenClaw*" --query 'Vpcs[0].VpcId' --output text)

# Install OpenClaw Operator
helm install openclaw-operator \
  oci://ghcr.io/openclaw-rocks/charts/openclaw-operator \
  --namespace openclaw-operator-system --create-namespace --version 0.20.0

# Apply K8s manifests
kubectl apply -f k8s/platform/namespace.yaml
envsubst < k8s/platform/rbac.yaml | kubectl apply -f -
envsubst < k8s/platform/service.yaml | kubectl apply -f -

# Create secret (deploy.sh does this automatically from CDK outputs)
# See deploy.sh create_platform_secret() for the full list of env vars

# Deploy
envsubst < k8s/platform/deployment.yaml | kubectl apply -f -
```

### 6. Verify

```bash
kubectl port-forward -n openclaw-platform svc/platform-api 8000:80
curl http://localhost:8000/health
# {"status":"ok","version":"0.9.50"}
```

## Destroy & Redeploy

When doing a full destroy + redeploy:

```bash
# 1. Clean up K8s resources first (avoids orphaned LBs/ENIs)
kubectl delete ns --all --field-selector metadata.name!=default,metadata.name!=kube-system,metadata.name!=kube-public,metadata.name!=kube-node-lease

# 2. Delete CDK stacks in reverse dependency order
aws cloudformation delete-stack --stack-name openclaw-saas-rds
aws cloudformation delete-stack --stack-name openclaw-saas-iam
# Wait for RDS + IAM...
# Empty S3 bucket before deleting stack:
aws s3 rm s3://openclaw-saas-backups-735091234506-cn-northwest-1 --recursive
aws cloudformation delete-stack --stack-name openclaw-saas-s3
aws cloudformation delete-stack --stack-name openclaw-saas-eks  # ~15-20 min
# Wait for EKS...
aws cloudformation delete-stack --stack-name openclaw-saas-sqs
# ECR repos with images need manual deletion:
for repo in openclaw-saas-platform openclaw-saas-billing-consumer openclaw-saas-metrics-exporter; do
  aws ecr delete-repository --repository-name $repo --force
done
aws cloudformation delete-stack --stack-name openclaw-saas-ecr
# Wait for ECR...
aws cloudformation delete-stack --stack-name openclaw-saas-vpc
```

## Known Issues & Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| CDK deploys to us-west-2 | CDK CLI uses default profile region | Set `aws_region` in `cdk.json` context |
| `kubectl: Unauthorized` | CDK-created cluster needs role assumption | Add `--role-arn` to `update-kubeconfig` |
| `sts:AssumeRole AccessDenied` | IAM user lacks permission | Add inline policy for `sts:AssumeRole` on `openclaw-saas-eks-*` |
| ECR stack fails `AlreadyExists` | Repos survive stack deletion | `aws ecr delete-repository --force` first |
| S3 stack fails `BucketNotEmpty` | Bucket has data | `aws s3 rm --recursive` first |
| EKS deletion takes 30+ min | Lambda VPC ENI cleanup is slow | Wait, or manually detach ENIs |
| `JSON.parse error` on frontend | Backend returns non-JSON 500 | Fixed in v0.9.49+ (api.js graceful handling) |
| `daily_usage table not found` | billing tables not auto-created | Fixed in v0.9.49+ (init_db creates billing tables) |

## Current Deployment

| Component | Status | Details |
|-----------|--------|---------|
| EKS | ✅ | `openclaw-saas-cluster`, K8s 1.30, 2× Graviton |
| Platform API | ✅ | `v0.9.50` (CN private ECR) |
| Operator | ✅ | v0.20.0 (Helm OCI) |
| ALB Controller | ✅ | kube-system |
| RDS | ✅ | PostgreSQL t4g.micro |

## Branch Workflow

```
main (Global) → cn (China) → cn-workshop
```

Generic fixes cherry-pick `main → cn`. CN-specific stays on `cn`. Never reverse-merge.
