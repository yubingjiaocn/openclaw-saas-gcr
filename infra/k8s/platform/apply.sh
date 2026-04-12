#!/usr/bin/env bash
set -euo pipefail

# Script to apply K8s platform manifests with variable substitution
# Usage: ./apply.sh
#
# Required environment variables:
#   PLATFORM_IMAGE    - Platform API container image (e.g., 956045422469.dkr.ecr.us-west-2.amazonaws.com/openclaw-saas-platform:v0.4.2)
#   ACM_CERT_ARN      - ACM certificate ARN for ALB ingress
#   DOMAIN_NAME       - Custom domain name for ingress

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Validate required variables
: "${PLATFORM_IMAGE:?PLATFORM_IMAGE is required}"
: "${ACM_CERT_ARN:?ACM_CERT_ARN is required}"
: "${DOMAIN_NAME:?DOMAIN_NAME is required}"

echo "==> Applying OpenClaw platform manifests..."
echo "    Platform Image: ${PLATFORM_IMAGE}"
echo "    ACM Cert ARN:   ${ACM_CERT_ARN}"
echo "    Domain Name:    ${DOMAIN_NAME}"

# Apply manifests with variable substitution
for manifest in namespace.yaml rbac.yaml service.yaml deployment.yaml ingress.yaml; do
  echo "    Applying ${manifest}..."
  envsubst < "${SCRIPT_DIR}/${manifest}" | kubectl apply -f -
done

echo "==> Platform manifests applied successfully!"
echo ""
echo "    To check status:"
echo "      kubectl get pods -n openclaw-platform"
echo "      kubectl get ingress -n openclaw-platform"
