#!/usr/bin/env bash
set -euo pipefail

# Apply K8s platform manifests with variable substitution.
#
# Required env:
#   PLATFORM_IMAGE   - e.g. <ECR>/openclaw-saas-platform:v0.9.55
#
# Optional env (ALB mode):
#   ACM_CERT_ARN     - ACM certificate ARN
#   DOMAIN_NAME      - Custom domain for ALB ingress
#
# If ACM_CERT_ARN + DOMAIN_NAME are set → ALB mode (applies ingress.yaml).
# Otherwise → NLB mode (service.yaml creates an internet-facing NLB via
# AWS Load Balancer Controller with loadBalancerClass).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${PLATFORM_IMAGE:?PLATFORM_IMAGE is required}"

# Determine deployment mode
if [[ -n "${ACM_CERT_ARN:-}" && -n "${DOMAIN_NAME:-}" ]]; then
  DEPLOY_MODE="alb"
  echo "==> Deployment mode: ALB + custom domain"
  echo "    Domain:   ${DOMAIN_NAME}"
  echo "    ACM ARN:  ${ACM_CERT_ARN}"
else
  DEPLOY_MODE="nlb"
  echo "==> Deployment mode: NLB (AWS LB Controller managed)"
fi
echo "    Image:    ${PLATFORM_IMAGE}"

# Apply base manifests (always)
for manifest in namespace.yaml rbac.yaml service.yaml deployment.yaml; do
  echo "    Applying ${manifest}..."
  envsubst < "${SCRIPT_DIR}/${manifest}" | kubectl apply -f -
done

# ALB mode: also apply ingress
if [[ "${DEPLOY_MODE}" == "alb" ]]; then
  echo "    Applying ingress.yaml..."
  envsubst < "${SCRIPT_DIR}/ingress.yaml" | kubectl apply -f -
fi

echo "==> Platform manifests applied successfully!"

# ── Wait for external endpoint ──
echo ""
if [[ "${DEPLOY_MODE}" == "nlb" ]]; then
  echo "==> Waiting for NLB endpoint..."
  LB_DNS=""
  for i in $(seq 1 36); do
    LB_DNS=$(kubectl get svc platform-api -n openclaw-platform \
      -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
    [[ -n "$LB_DNS" ]] && break
    echo "    Waiting... (${i}/36)"
    sleep 5
  done
  RESOURCE_CMD="kubectl get svc platform-api -n openclaw-platform"
else
  echo "==> Waiting for ALB endpoint..."
  LB_DNS=""
  for i in $(seq 1 36); do
    LB_DNS=$(kubectl get ingress platform-ingress -n openclaw-platform \
      -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
    [[ -n "$LB_DNS" ]] && break
    echo "    Waiting... (${i}/36)"
    sleep 5
  done
  RESOURCE_CMD="kubectl get ingress platform-ingress -n openclaw-platform"
fi

if [[ -n "${LB_DNS}" ]]; then
  echo "    Endpoint: http://${LB_DNS}"
  echo ""
  echo "    Verify:   curl -s http://${LB_DNS}/health"
else
  echo "    WARNING: Endpoint not available yet."
  echo "    Check:   ${RESOURCE_CMD}"
fi
