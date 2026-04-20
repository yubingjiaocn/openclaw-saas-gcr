#!/usr/bin/env bash
set -euo pipefail

# Apply K8s platform manifests with variable substitution.
#
# Required env:
#   PLATFORM_IMAGE        - e.g. public.ecr.aws/xxx/openclaw-saas-platform:v0.9.55
#
# Optional env — networking:
#   ACM_CERT_ARN          - ACM certificate ARN (ALB mode)
#   DOMAIN_NAME           - Custom domain for ALB ingress (ALB mode)
#   NLB_SG_PREFIX_LISTS   - Prefix list IDs for NLB SG inbound (empty = allow all)
#
# Optional env — billing:
#   BILLING_IMAGE         - Billing consumer image. If set, deploys as sidecar.
#
# Optional env — database:
#   DB_MODE               - "postgres" (default) or "sqlite"
#   SQLITE_STORAGE_CLASS  - StorageClass for SQLite PVC (default: gp3)
#   SQLITE_PVC_SIZE       - PVC size (default: 10Gi)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${PLATFORM_IMAGE:?PLATFORM_IMAGE is required}"

DB_MODE="${DB_MODE:-postgres}"
SQLITE_STORAGE_CLASS="${SQLITE_STORAGE_CLASS:-gp3}"
SQLITE_PVC_SIZE="${SQLITE_PVC_SIZE:-10Gi}"

# ── Determine modes ──
if [[ -n "${ACM_CERT_ARN:-}" && -n "${DOMAIN_NAME:-}" ]]; then
  DEPLOY_MODE="alb"
  echo "==> Networking: ALB + custom domain (${DOMAIN_NAME})"
else
  DEPLOY_MODE="nlb"
  echo "==> Networking: NLB (LB Controller managed)"
fi
echo "    Image:    ${PLATFORM_IMAGE}"
echo "    Billing:  ${BILLING_IMAGE:-<disabled>}"
echo "    Database: ${DB_MODE}"

# ── Pick deployment manifest ──
if [[ -n "${BILLING_IMAGE:-}" ]]; then
  DEPLOY_MANIFEST="deployment-with-billing.yaml"
else
  DEPLOY_MANIFEST="deployment.yaml"
fi

# ── SQLite: create PVC before deployment ──
if [[ "${DB_MODE}" == "sqlite" ]]; then
  echo "    Creating PVC for SQLite (${SQLITE_PVC_SIZE} on ${SQLITE_STORAGE_CLASS})..."
  cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: platform-data
  namespace: openclaw-platform
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: "${SQLITE_STORAGE_CLASS}"
  resources:
    requests:
      storage: ${SQLITE_PVC_SIZE}
EOF
fi

# ── Apply manifests ──
# namespace + rbac + service: straight envsubst
for manifest in namespace.yaml rbac.yaml service.yaml; do
  echo "    Applying ${manifest}..."
  envsubst < "${SCRIPT_DIR}/${manifest}" | kubectl apply -f -
done

# deployment: envsubst, then sqlite volume replacement if needed
echo "    Applying ${DEPLOY_MANIFEST} (DB_MODE=${DB_MODE})..."
if [[ "${DB_MODE}" == "sqlite" ]]; then
  # Replace emptyDir with PVC, and /app/data with /data (SQLite path)
  envsubst < "${SCRIPT_DIR}/${DEPLOY_MANIFEST}" | \
    sed -e 's|emptyDir: {}|persistentVolumeClaim:\n            claimName: platform-data|' \
        -e 's|/app/data|/data|g' | \
    kubectl apply -f -
else
  envsubst < "${SCRIPT_DIR}/${DEPLOY_MANIFEST}" | kubectl apply -f -
fi

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
