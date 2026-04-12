#!/usr/bin/env bash
set -euo pipefail

# Script to apply K8s platform manifests with variable substitution
# Usage: ./apply.sh
#
# Required environment variables:
#   PLATFORM_IMAGE    - Platform API container image
#
# Optional environment variables (for ALB + custom domain mode):
#   ACM_CERT_ARN      - ACM certificate ARN for ALB ingress
#   DOMAIN_NAME       - Custom domain name for ingress
#
# Modes:
#   NLB mode (default):  Only PLATFORM_IMAGE required. Creates an internet-facing
#                         NLB with CloudFront prefix list restriction.
#   ALB mode:            Set ACM_CERT_ARN and DOMAIN_NAME to also deploy ALB Ingress
#                         with HTTPS and custom domain.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CloudFront managed prefix list ID (us-east-1 / us-west-2 global)
CLOUDFRONT_PREFIX_LIST_ID="${CLOUDFRONT_PREFIX_LIST_ID:-pl-82a045eb}"

# Validate required variables
: "${PLATFORM_IMAGE:?PLATFORM_IMAGE is required}"

# Determine deployment mode
if [[ -n "${ACM_CERT_ARN:-}" && -n "${DOMAIN_NAME:-}" ]]; then
  DEPLOY_MODE="alb"
  echo "==> Deployment mode: ALB + custom domain"
  echo "    Platform Image: ${PLATFORM_IMAGE}"
  echo "    ACM Cert ARN:   ${ACM_CERT_ARN}"
  echo "    Domain Name:    ${DOMAIN_NAME}"
else
  DEPLOY_MODE="nlb"
  echo "==> Deployment mode: NLB (CloudFront prefix list restriction)"
  echo "    Platform Image: ${PLATFORM_IMAGE}"
fi

# Apply base manifests (always applied)
for manifest in namespace.yaml rbac.yaml service.yaml deployment.yaml; do
  echo "    Applying ${manifest}..."
  envsubst < "${SCRIPT_DIR}/${manifest}" | kubectl apply -f -
done

# Apply ingress only in ALB mode
if [[ "${DEPLOY_MODE}" == "alb" ]]; then
  echo "    Applying ingress.yaml..."
  envsubst < "${SCRIPT_DIR}/ingress.yaml" | kubectl apply -f -
fi

echo "==> Platform manifests applied successfully!"

# NLB mode: wait for NLB and configure security group with CloudFront prefix list
if [[ "${DEPLOY_MODE}" == "nlb" ]]; then
  echo ""
  echo "==> Waiting for NLB to be provisioned..."

  # Wait for the LoadBalancer hostname to appear (up to 3 minutes)
  for i in $(seq 1 36); do
    NLB_DNS=$(kubectl get svc platform-api -n openclaw-platform \
      -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
    if [[ -n "${NLB_DNS}" ]]; then
      break
    fi
    echo "    Waiting for NLB DNS... (${i}/36)"
    sleep 5
  done

  if [[ -z "${NLB_DNS:-}" ]]; then
    echo "    WARNING: NLB DNS not available yet. Check: kubectl get svc platform-api -n openclaw-platform"
  else
    echo "    NLB DNS: ${NLB_DNS}"

    # Extract NLB name from DNS (format: k8s-openclawp-platform-xxxx-yyyy.elb.region.amazonaws.com)
    NLB_NAME=$(echo "${NLB_DNS}" | cut -d'-' -f1-5 | sed 's/^/net\//' || true)

    # Find the NLB ARN to get its security group
    NLB_ARN=$(aws elbv2 describe-load-balancers \
      --query "LoadBalancers[?DNSName=='${NLB_DNS}'].LoadBalancerArn" \
      --output text 2>/dev/null || true)

    if [[ -n "${NLB_ARN}" ]]; then
      echo "    NLB ARN: ${NLB_ARN}"

      # Get the security group(s) attached to the NLB
      NLB_SG=$(aws elbv2 describe-load-balancers \
        --load-balancer-arns "${NLB_ARN}" \
        --query "LoadBalancers[0].SecurityGroups[0]" \
        --output text 2>/dev/null || true)

      if [[ -n "${NLB_SG}" && "${NLB_SG}" != "None" ]]; then
        echo "    NLB Security Group: ${NLB_SG}"
        echo "    Configuring CloudFront prefix list (${CLOUDFRONT_PREFIX_LIST_ID}) on SG..."

        # Revoke existing broad ingress rules on port 80 (if any)
        aws ec2 revoke-security-group-ingress \
          --group-id "${NLB_SG}" \
          --ip-permissions '[{"IpProtocol":"tcp","FromPort":80,"ToPort":80,"IpRanges":[{"CidrIp":"0.0.0.0/0"}]}]' \
          2>/dev/null || true

        # Add CloudFront prefix list rule
        aws ec2 authorize-security-group-ingress \
          --group-id "${NLB_SG}" \
          --ip-permissions "[{\"IpProtocol\":\"tcp\",\"FromPort\":80,\"ToPort\":80,\"PrefixListIds\":[{\"PrefixListId\":\"${CLOUDFRONT_PREFIX_LIST_ID}\",\"Description\":\"CloudFront prefix list\"}]}]" \
          2>/dev/null && echo "    CloudFront prefix list rule added to NLB SG." \
          || echo "    NOTE: Prefix list rule may already exist or requires manual configuration."
      else
        echo "    NOTE: NLB has no managed security group yet."
        echo "           The AWS LB Controller will create one shortly."
        echo "           Re-run this script or manually add the prefix list rule."
      fi
    fi
  fi

  echo ""
  echo "    To check NLB status:"
  echo "      kubectl get svc platform-api -n openclaw-platform"
  echo "      curl -s http://<NLB_DNS>/health"
else
  echo ""
  echo "    To check status:"
  echo "      kubectl get pods -n openclaw-platform"
  echo "      kubectl get ingress -n openclaw-platform"
fi
