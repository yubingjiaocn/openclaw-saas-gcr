# OpenClaw Custom Image for CN Region
# Pre-installs tools that cannot be fetched via npx (China firewall)
# Base: official OpenClaw image, User: node (uid 1000), HOME: /home/node
# Target: linux/arm64 (Graviton)
FROM public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw:2026.3.13-1

USER root

# ── System deps ──
RUN apt-get update && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

# ── Pre-install acpx into extension dir ──
# Base image has /app/extensions/acpx/package.json but no node_modules.
# Extract pinned version from config and install it.
RUN cd /app/extensions/acpx \
    && PINNED=$(node -e "console.log(JSON.parse(require('fs').readFileSync('package.json','utf8')).dependencies.acpx)") \
    && echo "Installing acpx@${PINNED}" \
    && npm install --omit=dev --no-save "acpx@${PINNED}" 2>&1 \
    && /app/extensions/acpx/node_modules/.bin/acpx --version

# ── Pre-install ACP agent binary (CN cannot use npx to download) ──
RUN npm install -g @zed-industries/claude-agent-acp@0.21.0

# ── Kiro CLI (native binary, headless, aarch64) ──
ARG KIRO_VERSION=1.28.0
RUN curl -fsSL "https://desktop-release.q.us-east-1.amazonaws.com/${KIRO_VERSION}/kirocli-aarch64-linux.tar.gz" \
    | tar xz -C /tmp \
    && cp /tmp/kirocli/bin/kiro-cli /usr/local/bin/ \
    && cp /tmp/kirocli/bin/kiro-cli-chat /usr/local/bin/ \
    && chmod +x /usr/local/bin/kiro-cli /usr/local/bin/kiro-cli-chat \
    && rm -rf /tmp/kirocli

# ── Kiro agent config (read-only, image layer) ──
# kiro-cli reads from ~/.kiro/agents/ — we put config directly there.
# Session data writes to ~/.kiro/sessions/ on overlay (non-persistent, same as claude/codex).
RUN mkdir -p /home/node/.kiro/agents /home/node/.kiro/settings
COPY kiro-agent-config.json /home/node/.kiro/agents/kiro_default.json
RUN echo '{"chat.defaultAgent":"kiro_default"}' > /home/node/.kiro/settings/cli.json \
    && chown -R 1000:1000 /home/node/.kiro

USER node

# ── Verify ──
RUN kiro-cli --version && jq --version \
    && claude-agent-acp --version \
    && /app/extensions/acpx/node_modules/.bin/acpx --version

LABEL org.opencontainers.image.title="openclaw-custom-cn" \
      org.opencontainers.image.description="OpenClaw CN region: pre-installed acpx + claude-agent-acp + kiro-cli" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"
