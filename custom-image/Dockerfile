# OpenClaw Custom Image with Kiro CLI + Tavily Search
# Base: official OpenClaw image (Debian bookworm, Node 24, Python 3.11)
# Target: linux/arm64 (Graviton)
#
# Runtime filesystem constraints (operator sets readOnlyRootFilesystem=true):
#   ❌ /home/openclaw/          — image layer, read-only (HOME dir)
#   ✅ /home/openclaw/.openclaw/ — PVC mount, writable (data root)
#   ✅ /home/openclaw/.cache/   — PVC subPath, writable
#   ✅ /home/openclaw/.local/   — PVC subPath, writable
#   ❌ /home/openclaw/.kiro/    — image layer, read-only (but readable)
#   ❌ /app/                    — image layer, read-only
#   ✅ /tmp/                    — emptyDir, writable
#
# This Dockerfile bakes tools + configs into the image layer.
# Files that need to land on the PVC (skills, playbook) are staged at
# /opt/openclaw-custom/ and copied by an init container at pod startup.
FROM ghcr.io/openclaw/openclaw:latest

USER root

# ── System deps ──
RUN apt-get update && apt-get install -y --no-install-recommends jq \
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

# ── acpx: pre-install into extension dir ──
# Base image ships /app/extensions/acpx/ with package.json but no node_modules.
# Runtime npm-install fails on readOnlyRootFilesystem (EROFS).
# Pre-install here so the runtime version check passes without re-install.
# `npm install --omit=dev` follows package.json's declared acpx version,
# so it automatically tracks the base image on upgrades.
RUN cd /app/extensions/acpx && npm install --omit=dev 2>&1 \
    && ls -la /app/extensions/acpx/node_modules/.bin/acpx \
    && /app/extensions/acpx/node_modules/.bin/acpx --version

# ── Kiro config (image layer, read-only but readable at runtime) ──
RUN mkdir -p /home/openclaw/.kiro/agents /home/openclaw/.kiro/settings
COPY kiro-agent-config.json /home/openclaw/.kiro/agents/kiro_default.json
RUN echo '{"chat.defaultAgent": "kiro_default"}' > /home/openclaw/.kiro/settings/cli.json \
    && chown -R 1000:1000 /home/openclaw/.kiro

# ── acpx symlink: ~/.acpx → ~/.openclaw/.acpx (PVC, writable) ──
RUN ln -sf /home/openclaw/.openclaw/.acpx /home/openclaw/.acpx \
    && chown -h 1000:1000 /home/openclaw/.acpx

# ── Staging area for PVC content (copied by init container) ──
RUN mkdir -p /opt/openclaw-custom/skills
COPY skills/search /opt/openclaw-custom/skills/search
COPY KIRO-PLAYBOOK.md /opt/openclaw-custom/KIRO-PLAYBOOK.md
RUN chmod +x /opt/openclaw-custom/skills/search/scripts/search.sh \
    && chown -R 1000:1000 /opt/openclaw-custom

USER node

# ── Verify ──
RUN kiro-cli --version && jq --version \
    && /app/extensions/acpx/node_modules/.bin/acpx --version \
    && ls /opt/openclaw-custom/skills/search/SKILL.md \
    && ls /opt/openclaw-custom/KIRO-PLAYBOOK.md

LABEL org.opencontainers.image.title="openclaw-custom" \
      org.opencontainers.image.description="OpenClaw with Kiro CLI + Tavily Search" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"
