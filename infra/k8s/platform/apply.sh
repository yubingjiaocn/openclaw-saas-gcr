#!/usr/bin/env bash
set -euo pipefail

# Apply K8s platform manifests with variable substitution.
#
# Required env:
#   PLATFORM_IMAGE        - e.g. <ECR>/openclaw-saas-platform:v0.9.55
#
# Optional env — networking:
#   ACM_CERT_ARN          - ACM certificate ARN (ALB mode)
#   DOMAIN_NAME           - Custom domain for ALB ingress (ALB mode)
#   NLB_SG_PREFIX_LISTS   - Comma-separated prefix list IDs for NLB SG inbound
#                           (e.g. CloudFront pl-xxx). Empty = allow all.
#
# Optional env — database:
#   DB_MODE               - "postgres" (default) or "sqlite"
#   SQLITE_STORAGE_CLASS  - StorageClass for SQLite PVC (default: gp3)
#   SQLITE_PVC_SIZE       - PVC size (default: 10Gi)
#
# Modes:
#   ACM_CERT_ARN + DOMAIN_NAME set → ALB ingress (HTTPS)
#   Otherwise                      → NLB service (HTTP)
#
#   DB_MODE=postgres → emptyDir volume (DB via DATABASE_URL in secret)
#   DB_MODE=sqlite   → EBS PVC at /data, DATABASE_URL=sqlite+aiosqlite:////data/platform.db

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${PLATFORM_IMAGE:?PLATFORM_IMAGE is required}"

DB_MODE="${DB_MODE:-postgres}"
SQLITE_STORAGE_CLASS="${SQLITE_STORAGE_CLASS:-gp3}"
SQLITE_PVC_SIZE="${SQLITE_PVC_SIZE:-10Gi}"

# ── Determine networking mode ──
if [[ -n "${ACM_CERT_ARN:-}" && -n "${DOMAIN_NAME:-}" ]]; then
  DEPLOY_MODE="alb"
  echo "==> Networking: ALB + custom domain (${DOMAIN_NAME})"
else
  DEPLOY_MODE="nlb"
  echo "==> Networking: NLB (LB Controller managed)"
fi
echo "    Image:    ${PLATFORM_IMAGE}"
echo "    Database: ${DB_MODE}"

# ── Choose deployment manifest ──
if [[ -n "${BILLING_IMAGE:-}" ]]; then
  DEPLOY_MANIFEST="deployment-with-billing.yaml"
else
  DEPLOY_MANIFEST="deployment.yaml"
fi

# ── Apply base manifests ──
for manifest in namespace.yaml rbac.yaml service.yaml "${DEPLOY_MANIFEST}"; do
  echo "    Applying ${manifest}..."
  envsubst < "${SCRIPT_DIR}/${manifest}" | kubectl apply -f -
done

# ALB mode: also apply ingress
if [[ "${DEPLOY_MODE}" == "alb" ]]; then
  echo "    Applying ingress.yaml..."
  envsubst < "${SCRIPT_DIR}/ingress.yaml" | kubectl apply -f -
fi

# ── SQLite mode: create PVC + patch deployment ──
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

  echo "    Patching deployment for SQLite PVC..."
  kubectl patch deployment platform-api -n openclaw-platform --type json -p '[
    {"op":"replace","path":"/spec/template/spec/volumes/0",
     "value":{"name":"data","persistentVolumeClaim":{"claimName":"platform-data"}}},
    {"op":"replace","path":"/spec/template/spec/containers/0/volumeMounts/0/mountPath",
     "value":"/data"}
  ]'
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
