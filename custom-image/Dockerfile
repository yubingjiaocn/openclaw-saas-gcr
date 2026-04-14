# OpenClaw Custom Image for CN Region
# Pre-installs tools that cannot be fetched via npx (China firewall)
# Base: official OpenClaw image, User: node (uid 1000), HOME: /home/node
# Target: linux/arm64 (Graviton)
# Build: docker buildx build --platform linux/arm64 -t openclaw-custom-cn .
FROM ghcr.io/openclaw/openclaw:latest

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
    && node -e "const p=JSON.parse(require('fs').readFileSync('package.json','utf8')); delete p.devDependencies; require('fs').writeFileSync('package.json',JSON.stringify(p,null,2))" \
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

# ── Kiro agent config ──
# Two copies of kiro config:
# 1. /home/node/.kiro/ — image layer, for non-persistent mode (fallback)
# 2. /opt/kiro-config/ — image layer, source for persistent mode
#
# For persistent kiro sessions, the .acpxrc.json wrapper sets
# HOME=~/.openclaw (PVC) and copies config from /opt/kiro-config/ first.
RUN mkdir -p /home/node/.kiro/agents /home/node/.kiro/settings \
    && mkdir -p /opt/kiro-config/agents /opt/kiro-config/settings
COPY kiro-agent-config.json /home/node/.kiro/agents/kiro_default.json
COPY kiro-agent-config.json /opt/kiro-config/agents/kiro_default.json
RUN echo '{"chat.defaultAgent":"kiro_default"}' | tee /home/node/.kiro/settings/cli.json > /opt/kiro-config/settings/cli.json \
    && chown -R 1000:1000 /home/node/.kiro /opt/kiro-config

USER node

# ── Verify ──
RUN kiro-cli --version && jq --version \
    && claude-agent-acp --version \
    && /app/extensions/acpx/node_modules/.bin/acpx --version

LABEL org.opencontainers.image.title="openclaw-custom-cn" \
      org.opencontainers.image.description="OpenClaw CN region: pre-installed acpx + claude-agent-acp + kiro-cli" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"
