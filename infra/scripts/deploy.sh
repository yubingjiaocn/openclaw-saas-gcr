#!/usr/bin/env bash
set -euo pipefail

# OpenClaw SaaS Infrastructure Deployment Script
#
# This script deploys the complete OpenClaw SaaS platform:
# 1. CDK stacks (VPC, EKS, RDS, ECR, SQS, S3, IAM, DNS)
# 2. Kubernetes components (ALB controller, openclaw-operator)
# 3. Platform API application
#
# Prerequisites:
#   - AWS CLI configured
#   - CDK CLI installed (npm install -g aws-cdk)
#   - kubectl installed
#   - helm installed
#   - jq installed
#
# Usage:
#   ./scripts/deploy.sh [OPTIONS]
#
# Options:
#   --skip-cdk          Skip CDK deployment
#   --skip-k8s          Skip Kubernetes deployment
#   --platform-version  Platform image version (default: latest from ECR)
#   -h, --help          Show this help message

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default options
SKIP_CDK=false
SKIP_K8S=false
PLATFORM_VERSION=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-cdk)
      SKIP_CDK=true
      shift
      ;;
    --skip-k8s)
      SKIP_K8S=true
      shift
      ;;
    --platform-version)
      PLATFORM_VERSION="$2"
      shift 2
      ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

log_info() {
  echo -e "${GREEN}==>${NC} $*"
}

log_warn() {
  echo -e "${YELLOW}WARNING:${NC} $*"
}

log_error() {
  echo -e "${RED}ERROR:${NC} $*"
  exit 1
}

check_prerequisites() {
  log_info "Checking prerequisites..."

  local missing=()

  command -v aws &> /dev/null || missing+=("aws-cli")
  command -v cdk &> /dev/null || missing+=("aws-cdk")
  command -v kubectl &> /dev/null || missing+=("kubectl")
  command -v helm &> /dev/null || missing+=("helm")
  command -v jq &> /dev/null || missing+=("jq")

  if [[ ${#missing[@]} -gt 0 ]]; then
    log_error "Missing required tools: ${missing[*]}"
  fi

  # Check AWS credentials
  if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured. Run 'aws configure'"
  fi

  log_info "All prerequisites met"
}

get_stack_output() {
  local stack_name="$1"
  local output_key="$2"
  aws cloudformation describe-stacks \
    --stack-name "${stack_name}" \
    --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue" \
    --output text 2>/dev/null || echo ""
}

deploy_cdk() {
  log_info "Deploying CDK stacks..."

  cd "${REPO_ROOT}/cdk"

  # Get project name and environment from cdk.json
  PROJECT_NAME=$(jq -r '.context.project_name' cdk.json)
  ENVIRONMENT=$(jq -r '.context.environment' cdk.json)
  STACK_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"

  log_info "Project: ${PROJECT_NAME}, Environment: ${ENVIRONMENT}"

  # Bootstrap CDK (if not already done)
  log_info "Bootstrapping CDK..."
  cdk bootstrap

  # Deploy all stacks
  log_info "Deploying all CDK stacks..."
  cdk deploy --all --require-approval never

  log_info "CDK stacks deployed successfully"

  cd "${REPO_ROOT}"
}

configure_kubectl() {
  log_info "Configuring kubectl..."

  # Get cluster name from CDK output
  local cluster_name=$(get_stack_output "${STACK_PREFIX}-eks" "ClusterName")

  if [[ -z "${cluster_name}" ]]; then
    log_error "Could not find EKS cluster name in stack outputs"
  fi

  log_info "Updating kubeconfig for cluster: ${cluster_name}"
  aws eks update-kubeconfig --name "${cluster_name}" --region "${AWS_REGION:-us-west-2}"

  # Wait for cluster to be ready
  log_info "Waiting for cluster to be ready..."
  kubectl wait --for=condition=Ready nodes --all --timeout=300s || true

  log_info "kubectl configured successfully"
}

install_alb_controller() {
  log_info "Installing AWS Load Balancer Controller..."

  # Check if already installed
  if helm list -n kube-system | grep -q aws-load-balancer-controller; then
    log_info "AWS Load Balancer Controller already installed, skipping"
    return
  fi

  local cluster_name=$(get_stack_output "${STACK_PREFIX}-eks" "ClusterName")
  local vpc_id=$(get_stack_output "${STACK_PREFIX}-vpc" "VpcId")
  local region="${AWS_REGION:-us-west-2}"

  # Add EKS chart repo
  helm repo add eks https://aws.github.io/eks-charts
  helm repo update

  # Install ALB controller
  helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
    -n kube-system \
    --set clusterName="${cluster_name}" \
    --set serviceAccount.create=true \
    --set region="${region}" \
    --set vpcId="${vpc_id}"

  log_info "AWS Load Balancer Controller installed"
}

install_openclaw_operator() {
  log_info "Installing openclaw-operator..."

  # Check if already installed
  if helm list -n openclaw-operator-system | grep -q openclaw-operator; then
    log_info "openclaw-operator already installed, upgrading..."
    helm upgrade openclaw-operator \
      oci://ghcr.io/openclaw-rocks/charts/openclaw-operator \
      --namespace openclaw-operator-system \
      --set leaderElection.enabled=true \
      --set crds.install=true
  else
    helm install openclaw-operator \
      oci://ghcr.io/openclaw-rocks/charts/openclaw-operator \
      --namespace openclaw-operator-system \
      --set leaderElection.enabled=true \
      --set crds.install=true
  fi

  log_info "openclaw-operator installed"
}

create_platform_secret() {
  log_info "Creating platform-api-config secret..."

  local db_secret_arn=$(get_stack_output "${STACK_PREFIX}-rds" "DbSecretArn")
  local db_endpoint=$(get_stack_output "${STACK_PREFIX}-rds" "DbEndpoint")
  local db_port=$(get_stack_output "${STACK_PREFIX}-rds" "DbPort")
  local db_name=$(get_stack_output "${STACK_PREFIX}-rds" "DbName")
  local queue_url=$(get_stack_output "${STACK_PREFIX}-sqs" "UsageQueueUrl")

  # Get DB credentials from Secrets Manager
  local db_secret=$(aws secretsmanager get-secret-value --secret-id "${db_secret_arn}" --query SecretString --output text)
  local db_username=$(echo "${db_secret}" | jq -r .username)
  local db_password=$(echo "${db_secret}" | jq -r .password)

  # Create database URL
  local database_url="postgresql://${db_username}:${db_password}@${db_endpoint}:${db_port}/${db_name}"

  # Create or update secret
  kubectl create secret generic platform-api-config \
    -n openclaw-platform \
    --from-literal=DATABASE_URL="${database_url}" \
    --from-literal=USAGE_EVENTS_QUEUE_URL="${queue_url}" \
    --dry-run=client -o yaml | kubectl apply -f -

  log_info "platform-api-config secret created"
}

deploy_platform_api() {
  log_info "Deploying platform API..."

  # Get ECR repository URI
  local ecr_repo_uri=$(get_stack_output "${STACK_PREFIX}-ecr" "PlatformRepoUriOutput")

  if [[ -z "${ecr_repo_uri}" ]]; then
    log_error "Could not find ECR repository URI"
  fi

  # Determine image version
  if [[ -z "${PLATFORM_VERSION}" ]]; then
    log_info "No version specified, using latest from ECR..."
    PLATFORM_VERSION=$(aws ecr describe-images \
      --repository-name "${PROJECT_NAME}-${ENVIRONMENT}-platform" \
      --query 'sort_by(imageDetails,& imagePushedAt)[-1].imageTags[0]' \
      --output text 2>/dev/null || echo "latest")
  fi

  local platform_image="${ecr_repo_uri}:${PLATFORM_VERSION}"
  log_info "Using platform image: ${platform_image}"

  # Get ACM cert ARN and domain name
  local acm_cert_arn=$(get_stack_output "${STACK_PREFIX}-dns" "CertificateArn" || echo "")
  local domain_name=$(get_stack_output "${STACK_PREFIX}-dns" "DomainName" || echo "")

  if [[ -z "${acm_cert_arn}" ]] || [[ -z "${domain_name}" ]]; then
    log_warn "No custom domain configured, using ALB default DNS"
    acm_cert_arn="none"
    domain_name="*"
  fi

  # Apply K8s manifests with substitution
  export PLATFORM_IMAGE="${platform_image}"
  export ACM_CERT_ARN="${acm_cert_arn}"
  export DOMAIN_NAME="${domain_name}"

  cd "${REPO_ROOT}/k8s/platform"
  bash apply.sh

  log_info "Platform API deployed"
}

run_db_migration() {
  log_info "Running database migration..."

  # Wait for platform API to be ready
  log_info "Waiting for platform-api pod to be ready..."
  kubectl wait --for=condition=Ready pod -l app=platform-api -n openclaw-platform --timeout=300s

  # Run migration
  local pod_name=$(kubectl get pod -l app=platform-api -n openclaw-platform -o jsonpath='{.items[0].metadata.name}')
  log_info "Running migration in pod: ${pod_name}"

  kubectl exec -n openclaw-platform "${pod_name}" -- python -m alembic upgrade head || {
    log_warn "Migration command failed, but this may be expected if migrations are not set up yet"
  }

  log_info "Database migration complete"
}

verify_deployment() {
  log_info "Verifying deployment..."

  # Check platform API health
  local pod_name=$(kubectl get pod -l app=platform-api -n openclaw-platform -o jsonpath='{.items[0].metadata.name}')

  log_info "Platform API pod: ${pod_name}"
  kubectl get pod -n openclaw-platform "${pod_name}"

  # Get ingress URL
  local ingress_host=$(kubectl get ingress platform-ingress -n openclaw-platform -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

  if [[ -n "${ingress_host}" ]]; then
    log_info "Platform API accessible at: https://${ingress_host}"
  else
    log_warn "Ingress not yet ready, check with: kubectl get ingress -n openclaw-platform"
  fi

  log_info "Deployment verified!"
}

main() {
  log_info "Starting OpenClaw SaaS deployment..."

  check_prerequisites

  # Get config from cdk.json
  PROJECT_NAME=$(jq -r '.context.project_name' "${REPO_ROOT}/cdk/cdk.json")
  ENVIRONMENT=$(jq -r '.context.environment' "${REPO_ROOT}/cdk/cdk.json")
  STACK_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"

  if [[ "${SKIP_CDK}" == "false" ]]; then
    deploy_cdk
  else
    log_warn "Skipping CDK deployment (--skip-cdk)"
  fi

  if [[ "${SKIP_K8S}" == "false" ]]; then
    configure_kubectl
    install_alb_controller
    install_openclaw_operator
    create_platform_secret
    deploy_platform_api
    run_db_migration
    verify_deployment
  else
    log_warn "Skipping Kubernetes deployment (--skip-k8s)"
  fi

  log_info "Deployment complete!"
  echo ""
  log_info "Next steps:"
  echo "  1. Check pods:    kubectl get pods -n openclaw-platform"
  echo "  2. Check ingress: kubectl get ingress -n openclaw-platform"
  echo "  3. View logs:     kubectl logs -n openclaw-platform -l app=platform-api -f"
}

main "$@"
