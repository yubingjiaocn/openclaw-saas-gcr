# OpenClaw Custom Image with Kiro CLI + Tavily Search
# Base: official OpenClaw image (Debian bookworm, Node 24, Python 3.11)
# Target: linux/arm64 (Graviton)
#
# acpx: Pre-install the EXACT pinned version into /app/extensions/acpx/node_modules
# at build time. The operator sets readOnlyRootFilesystem=true, so the runtime
# npm-install fallback fails. The version MUST match ACPX_PINNED_VERSION in
# /app/extensions/acpx/src/config.ts — a mismatch triggers re-install → fails.
# Do NOT install acpx globally or override with a different version.
FROM ghcr.io/openclaw/openclaw:latest

# ── System deps (as root) ──
USER root

# jq is needed by tavily-search skill
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

# ── acpx: pre-install pinned version into the extension dir ──
# The base image ships /app/extensions/acpx/ WITHOUT node_modules.
# At runtime, OpenClaw calls ensureAcpx() which tries `npm install` into that dir.
# With readOnlyRootFilesystem=true (set by operator), npm install fails → ACP broken.
# Pre-installing at build time bakes the binary into the image layer (read-only but present).
#
# MUST match ACPX_PINNED_VERSION in /app/extensions/acpx/src/config.ts.
# A version mismatch triggers re-install → fails on readOnly → ACP broken.
RUN cd /app/extensions/acpx && npm install --omit=dev --no-save acpx@0.1.15 2>&1 \
    && ls -la /app/extensions/acpx/node_modules/.bin/acpx

# ── Kiro agent config (baked into image layer) ──
# CRITICAL: operator sets readOnlyRootFilesystem=true + HOME=/home/openclaw
# Only /home/openclaw/.openclaw (PVC), /home/openclaw/.cache (PVC subPath),
# /home/openclaw/.local (PVC subPath), /tmp (emptyDir), and image-layer files
# are writable at runtime.

# Kiro agent config
RUN mkdir -p /home/openclaw/.kiro/agents /home/openclaw/.kiro/settings
COPY kiro-agent-config.json /home/openclaw/.kiro/agents/kiro_default.json
RUN echo '{"chat.defaultAgent": "kiro_default"}' > /home/openclaw/.kiro/settings/cli.json

# acpx session data directory — symlink to PVC-backed path.
# /home/openclaw/ is read-only at runtime (readOnlyRootFilesystem) but
# /home/openclaw/.openclaw/ is a PVC mount (writable). Create a symlink so
# acpx writes to ~/.acpx → ~/.openclaw/.acpx (writable PVC).
# The target dir is created by the init-config container (operator-managed)
# or lazily by acpx's mkdir call following the symlink into the writable PVC.
RUN ln -sf /home/openclaw/.openclaw/.acpx /home/openclaw/.acpx \
    && chown -h 1000:1000 /home/openclaw/.acpx

# Fix ownership
RUN chown -R 1000:1000 /home/openclaw/.kiro

# Also keep copies at /home/node/ for build-time verification
RUN mkdir -p /home/node/.kiro/agents /home/node/.kiro/settings && \
    cp /home/openclaw/.kiro/agents/kiro_default.json /home/node/.kiro/agents/kiro_default.json && \
    cp /home/openclaw/.kiro/settings/cli.json /home/node/.kiro/settings/cli.json && \
    chown -R node:node /home/node/.kiro

# ── Tavily Search skill ──
COPY skills/search /home/node/.openclaw/skills/search
RUN chmod +x /home/node/.openclaw/skills/search/scripts/search.sh \
    && chown -R node:node /home/node/.openclaw/skills

# ── KIRO-PLAYBOOK.md ──
COPY KIRO-PLAYBOOK.md /home/node/.openclaw/workspace/KIRO-PLAYBOOK.md
RUN chown node:node /home/node/.openclaw/workspace/KIRO-PLAYBOOK.md

# ── Back to non-root user ──
USER node

# Verify
RUN kiro-cli --version && jq --version && \
    /app/extensions/acpx/node_modules/.bin/acpx --version && \
    cat /home/openclaw/.kiro/agents/kiro_default.json | jq .name && \
    cat /home/openclaw/.kiro/settings/cli.json | jq .

# ── Labels ──
LABEL org.opencontainers.image.title="openclaw-custom" \
      org.opencontainers.image.description="OpenClaw with Kiro CLI + Tavily Search" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"
