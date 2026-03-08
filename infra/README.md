# OpenClaw SaaS Infrastructure

Fully parameterized AWS CDK infrastructure and Kubernetes manifests for the OpenClaw SaaS platform on EKS.

## Features

- **Fully Parameterized**: Deploy to any AWS account/region with just configuration changes
- **Production-Ready**: RDS PostgreSQL, SQS, ECR, S3, ALB Ingress, IRSA
- **Cost-Optimized**: Graviton nodes, single NAT gateway, VPC endpoints
- **Secure**: Private subnets, encrypted storage, Secrets Manager, security groups
- **Automated**: Single script deployment from infrastructure to application

## Components

| Directory | Description |
|-----------|-------------|
| `cdk/` | AWS CDK stacks (VPC, EKS, RDS, S3, DNS/ACM, SQS, ECR, IAM) |
| `k8s/platform/` | Parameterized Kubernetes manifests for platform API |
| `scripts/` | Automated deployment scripts |
| `observability/` | Prometheus, Grafana, Loki |
| `cicd/` | GitHub Actions workflows |
| `docs/` | Runbook, disaster recovery |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ VPC (2 AZs)                                          │  │
│  │  ┌──────────────┐          ┌──────────────┐          │  │
│  │  │ Public Subnet│          │ Public Subnet│          │  │
│  │  │   NAT GW     │          │              │          │  │
│  │  └──────┬───────┘          └──────────────┘          │  │
│  │         │                                             │  │
│  │  ┌──────┴───────┐          ┌──────────────┐          │  │
│  │  │Private Subnet│          │Private Subnet│          │  │
│  │  │              │          │              │          │  │
│  │  │ ┌──────────┐ │          │ ┌──────────┐ │          │  │
│  │  │ │ EKS Nodes│ │          │ │ EKS Nodes│ │          │  │
│  │  │ │  t4g.*   │ │          │ │  t4g.*   │ │          │  │
│  │  │ └──────────┘ │          │ └──────────┘ │          │  │
│  │  │              │          │              │          │  │
│  │  │ ┌──────────┐ │          │ ┌──────────┐ │          │  │
│  │  │ │    RDS   │ │          │ │RDS Replica│ │          │  │
│  │  │ │PostgreSQL│ │          │ │ (optional)│ │          │  │
│  │  │ └──────────┘ │          │ └──────────┘ │          │  │
│  │  └──────────────┘          └──────────────┘          │  │
│  │                                                        │  │
│  │  VPC Endpoints: S3, ECR, STS                          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │     ECR     │  │     SQS     │  │     S3      │          │
│  │ (3 repos)   │  │ (usage evt) │  │  (backups)  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐                           │
│  │     ACM     │  │  Route53    │                           │
│  │   (cert)    │  │   (DNS)     │                           │
│  └─────────────┘  └─────────────┘                           │
└───────────────────────────────────────────────────────────────┘

                          ↓ ALB Ingress ↓

                     Internet Users
```

## Quick Start

### Prerequisites

Install the following tools:

```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# CDK CLI
npm install -g aws-cdk

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# jq
sudo apt-get install jq  # Ubuntu/Debian
# or: brew install jq    # macOS
```

Configure AWS credentials:

```bash
aws configure
# AWS Access Key ID: YOUR_KEY
# AWS Secret Access Key: YOUR_SECRET
# Default region name: us-west-2
# Default output format: json
```

### Option 1: Automated Deployment (Recommended)

The easiest way to deploy is using the automated script:

```bash
# 1. Install Python dependencies
cd cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# 2. Configure deployment (edit cdk/cdk.json)
# See Configuration Reference below

# 3. Run deployment script
./scripts/deploy.sh
```

This script will:
- Deploy all CDK stacks
- Configure kubectl
- Install ALB controller and openclaw-operator
- Deploy platform API
- Run database migrations
- Verify deployment

### Option 2: Manual Deployment

```bash
# 1. Install Python dependencies
cd cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Bootstrap CDK (first time only)
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-west-2
cdk bootstrap

# 3. Deploy CDK stacks
cdk deploy --all --require-approval never

# 4. Configure kubectl
CLUSTER_NAME=$(aws cloudformation describe-stacks \
  --stack-name openclaw-saas-dev-eks \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterName'].OutputValue" \
  --output text)
aws eks update-kubeconfig --name ${CLUSTER_NAME} --region ${CDK_DEFAULT_REGION}

# 5. Install ALB controller
helm repo add eks https://aws.github.io/eks-charts
helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=${CLUSTER_NAME} \
  --set serviceAccount.create=true

# 6. Install openclaw-operator
helm install openclaw-operator \
  oci://ghcr.io/openclaw-rocks/charts/openclaw-operator \
  --namespace openclaw-operator-system \
  --set leaderElection.enabled=true \
  --set crds.install=true

# 7. Deploy platform API
cd ../k8s/platform
export PLATFORM_IMAGE="<your-ecr-repo>/openclaw-saas-platform:latest"
export ACM_CERT_ARN="<your-cert-arn>"
export DOMAIN_NAME="<your-domain>"
./apply.sh
```

## Configuration Reference

All configuration is managed in `cdk/cdk.json`. Edit the `context` section:

### Core Configuration

```json
{
  "project_name": "openclaw-saas",    // Project identifier
  "environment": "dev",                // Environment: dev/staging/prod
}
```

### Domain and SSL (Optional)

```json
{
  "domain_name": "openclaw.example.com",           // Custom domain (leave empty to skip)
  "hosted_zone_id": "Z1234567890ABC",              // Route53 hosted zone ID
  "hosted_zone_name": "example.com",               // Route53 zone name
  "acm_cert_arn": "arn:aws:acm:...:certificate/..." // Existing cert ARN (or leave empty to create)
}
```

**Note**: If `domain_name` is empty, the platform will use the ALB's default DNS name.

### Database Configuration

```json
{
  "db_instance_class": "db.t4g.micro",  // RDS instance type
  "db_name": "openclawsaas",             // Database name
  "db_allocated_storage": 20,            // Initial storage (GB)
  "db_max_allocated_storage": 100        // Max autoscaling storage (GB)
}
```

### EKS Configuration

```json
{
  "eks_node_instance_type": "t4g.medium", // Node instance type (ARM64)
  "eks_node_min": 2,                      // Min nodes
  "eks_node_max": 5,                      // Max nodes
  "eks_node_desired": 2,                  // Desired nodes
  "eks_node_disk_size": 50,               // Node disk size (GB)
  "eks_version": "1.30"                   // Kubernetes version
}
```

### VPC Configuration

```json
{
  "vpc_max_azs": 2,              // Number of availability zones
  "enable_nat_gateway": true,    // Enable NAT gateway
  "nat_gateways": 1              // Number of NAT gateways (1 for cost savings)
}
```

### SQS Configuration

```json
{
  "sqs_visibility_timeout": 60,      // Message visibility timeout (seconds)
  "sqs_retention_period_days": 14,   // Message retention period
  "sqs_receive_wait_time": 20,       // Long polling wait time (seconds)
  "sqs_max_receive_count": 5         // Max receives before DLQ
}
```

### Storage Configuration

```json
{
  "s3_lifecycle_transition_days": 30, // Days before transitioning to IA
  "ecr_image_count_limit": 10         // Max images to keep per repo
}
```

## Deployment to Different Environments

### Development Environment

Use default configuration in `cdk.json` (no custom domain needed):

```bash
./scripts/deploy.sh
```

### Production Environment

1. Create `cdk.prod.json` with production configuration
2. Deploy with custom context:

```bash
cd cdk
cdk deploy --all -c project_name=openclaw-saas -c environment=prod \
  -c domain_name=openclaw.example.com \
  -c hosted_zone_id=Z1234567890ABC \
  -c db_instance_class=db.t4g.small \
  -c eks_node_instance_type=t4g.large
```

### Multi-Region Deployment

Simply set different AWS region and deploy:

```bash
export CDK_DEFAULT_REGION=eu-west-1
./scripts/deploy.sh
```

All resources will be created in the specified region.

## Stack Outputs

After deployment, useful outputs are available:

```bash
# Get all stack outputs
aws cloudformation describe-stacks --stack-name openclaw-saas-dev-eks --query "Stacks[0].Outputs"

# Specific outputs
CLUSTER_NAME=$(aws cloudformation describe-stacks --stack-name openclaw-saas-dev-eks \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterName'].OutputValue" --output text)

DB_ENDPOINT=$(aws cloudformation describe-stacks --stack-name openclaw-saas-dev-rds \
  --query "Stacks[0].Outputs[?OutputKey=='DbEndpoint'].OutputValue" --output text)

ECR_REPO=$(aws cloudformation describe-stacks --stack-name openclaw-saas-dev-ecr \
  --query "Stacks[0].Outputs[?OutputKey=='PlatformRepoUriOutput'].OutputValue" --output text)
```

## Infrastructure Details

### CDK Stacks

| Stack | Resources | Purpose |
|-------|-----------|---------|
| VPC | VPC, Subnets, NAT, VPC Endpoints | Network foundation |
| EKS | EKS Cluster, Node Groups, Addons | Kubernetes control plane |
| RDS | PostgreSQL 16, Secrets, Security Groups | Application database |
| ECR | 3 repositories with lifecycle policies | Container images |
| SQS | Usage events queue + DLQ | Async processing |
| S3 | Backups bucket with lifecycle | Backups and artifacts |
| IAM | IRSA roles, node policies | Access control |
| DNS | ACM certificate, Route53 (optional) | SSL and DNS |

### Kubernetes Components

- **openclaw-operator**: Manages OpenClawInstance CRDs
- **AWS Load Balancer Controller**: Provisions ALB for ingresses
- **EBS CSI Driver**: Persistent storage for stateful workloads
- **platform-api**: Multi-tenant control plane API

### Security

- All traffic in private subnets (EKS nodes, RDS)
- ALB in public subnets for ingress
- Encrypted storage (EBS, RDS, S3)
- Secrets Manager for DB credentials
- IRSA (IAM Roles for Service Accounts) for pod permissions
- Security groups restrict access between components

## Operations

### Scaling

```bash
# Scale EKS nodes
aws eks update-nodegroup-config \
  --cluster-name ${CLUSTER_NAME} \
  --nodegroup-name GravitonNodes \
  --scaling-config minSize=3,maxSize=10,desiredSize=5

# Scale platform API
kubectl scale deployment platform-api -n openclaw-platform --replicas=3
```

### Database Access

```bash
# Get DB credentials from Secrets Manager
DB_SECRET_ARN=$(aws cloudformation describe-stacks --stack-name openclaw-saas-dev-rds \
  --query "Stacks[0].Outputs[?OutputKey=='DbSecretArn'].OutputValue" --output text)

aws secretsmanager get-secret-value --secret-id ${DB_SECRET_ARN} --query SecretString --output text | jq

# Port-forward to access DB
kubectl run psql-client --rm -it --image=postgres:16-alpine -- \
  psql "postgresql://username:password@endpoint:5432/dbname"
```

### Logs

```bash
# Platform API logs
kubectl logs -n openclaw-platform -l app=platform-api -f

# OpenClawInstance logs
kubectl logs -n tenant-123 -l app=openclaw -f
```

### Monitoring

Check observability/ directory for Prometheus, Grafana, and Loki setup.

## Troubleshooting

### CDK Deployment Fails

```bash
# Check CloudFormation events
aws cloudformation describe-stack-events --stack-name openclaw-saas-dev-vpc

# Rollback and retry
cdk destroy openclaw-saas-dev-vpc
cdk deploy openclaw-saas-dev-vpc
```

### Platform API Not Starting

```bash
# Check pod status
kubectl describe pod -n openclaw-platform -l app=platform-api

# Check logs
kubectl logs -n openclaw-platform -l app=platform-api --previous

# Check secret exists
kubectl get secret platform-api-config -n openclaw-platform
```

### ALB Not Provisioned

```bash
# Check ALB controller logs
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller -f

# Check ingress status
kubectl describe ingress platform-ingress -n openclaw-platform
```

## Cleanup

```bash
# Delete all OpenClawInstances first
kubectl delete openclawinstance --all --all-namespaces

# Delete platform resources
kubectl delete namespace openclaw-platform

# Destroy CDK stacks
cd cdk
cdk destroy --all
```

**Note**: RDS will create a final snapshot before deletion. S3 buckets and ECR repos have `RETAIN` policy.

## Cost Optimization

Current setup is optimized for dev/test with ~$150-200/month AWS costs:

- **EKS**: ~$73/month (control plane)
- **EC2**: ~$30/month (2x t4g.medium nodes)
- **RDS**: ~$13/month (db.t4g.micro)
- **NAT Gateway**: ~$32/month
- **Other**: ~$20/month (ALB, VPC endpoints, storage)

Production optimizations:
- Use reserved instances for nodes
- Multi-AZ RDS for HA (~2x cost)
- More NAT gateways for HA (~$32/month each)
- CloudFront CDN for global distribution

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

[License information]
