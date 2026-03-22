# OpenClaw Custom Image with Kiro CLI + acpx + Tavily Search
# Base: official OpenClaw image (Debian bookworm, Node 24, Python 3.11)
# Target: linux/arm64 (Graviton)
FROM ghcr.io/openclaw/openclaw:latest

# ── System deps (as root) ──
USER root

# jq is needed by tavily-search skill + acpx config
RUN apt-get update && apt-get install -y --no-install-recommends \
        jq \
    && rm -rf /var/lib/apt/lists/*

# ── Kiro CLI (native binary, headless, aarch64) ──
ARG KIRO_VERSION=1.28.0
RUN set -e \
    && curl -fsSL "https://desktop-release.q.us-east-1.amazonaws.com/${KIRO_VERSION}/kirocli-aarch64-linux.tar.gz" \
       -o /tmp/kirocli.tar.gz \
    && tar xzf /tmp/kirocli.tar.gz -C /tmp \
    && cp /tmp/kirocli/bin/kiro-cli /usr/local/bin/kiro-cli \
    && cp /tmp/kirocli/bin/kiro-cli-chat /usr/local/bin/kiro-cli-chat \
    && chmod +x /usr/local/bin/kiro-cli /usr/local/bin/kiro-cli-chat \
    && rm -rf /tmp/kirocli /tmp/kirocli.tar.gz \
    && kiro-cli --version

# ── acpx: use OpenClaw's built-in acpx (do NOT override version) ──
# OpenClaw bundles acpx in /app/extensions/acpx/node_modules/.bin/acpx
# with a pinned version. Installing a different version causes a mismatch
# and runtime failure (npm install fallback fails on read-only filesystem).
# We only install acpx globally for CLI convenience (e.g. `acpx config show`).
RUN npm install -g acpx@latest && acpx --version

# ── Kiro + acpx config (baked into image layer) ──
# CRITICAL: operator sets readOnlyRootFilesystem=true + HOME=/home/openclaw
# Only /home/openclaw/.openclaw (PVC), /tmp (emptyDir), and image-layer files are accessible.
# We pre-create ALL config at /home/openclaw/ so they exist in the read-only image layer.

# acpx config
COPY acpx-config.json /home/openclaw/.acpx/config.json

# Kiro agent config
RUN mkdir -p /home/openclaw/.kiro/agents /home/openclaw/.kiro/settings
COPY kiro-agent-config.json /home/openclaw/.kiro/agents/kiro_default.json
RUN echo '{"chat.defaultAgent": "kiro_default"}' > /home/openclaw/.kiro/settings/cli.json

# Fix ownership
RUN chown -R 1000:1000 /home/openclaw/.acpx /home/openclaw/.kiro

# Also keep copies at /home/node/ for build-time verification
RUN mkdir -p /home/node/.acpx /home/node/.kiro/agents /home/node/.kiro/settings && \
    cp /home/openclaw/.acpx/config.json /home/node/.acpx/config.json && \
    cp /home/openclaw/.kiro/agents/kiro_default.json /home/node/.kiro/agents/kiro_default.json && \
    cp /home/openclaw/.kiro/settings/cli.json /home/node/.kiro/settings/cli.json && \
    chown -R node:node /home/node/.acpx /home/node/.kiro

# ── Tavily Search skill ──
COPY skills/search /home/node/.openclaw/skills/search
RUN chmod +x /home/node/.openclaw/skills/search/scripts/search.sh \
    && chown -R node:node /home/node/.openclaw/skills

# ── KIRO-PLAYBOOK.md ──
COPY KIRO-PLAYBOOK.md /home/node/.openclaw/workspace/KIRO-PLAYBOOK.md
RUN chown node:node /home/node/.openclaw/workspace/KIRO-PLAYBOOK.md

# ── Back to non-root user ──
USER node

# Verify (use HOME=/home/openclaw to match runtime)
RUN kiro-cli --version && acpx --version && jq --version && \
    HOME=/home/openclaw acpx config show 2>/dev/null | jq '.agents.kiro' && \
    cat /home/openclaw/.kiro/agents/kiro_default.json | jq .name && \
    cat /home/openclaw/.kiro/settings/cli.json | jq .

# ── Labels ──
LABEL org.opencontainers.image.title="openclaw-custom" \
      org.opencontainers.image.description="OpenClaw with Kiro CLI + acpx + Tavily Search" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"
