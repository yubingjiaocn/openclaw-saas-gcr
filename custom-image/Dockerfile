# OpenClaw Custom Image with Kiro CLI + Tavily Search
# Base: official OpenClaw image (Debian bookworm, Node 24, Python 3.11)
# Target: linux/arm64 (Graviton)
#
# Runtime filesystem constraints (operator sets readOnlyRootFilesystem=true):
#   ❌ /home/openclaw/          — image layer, read-only (HOME dir)
#   ✅ /home/openclaw/.openclaw/ — PVC mount, writable (data root)
#   ✅ /home/openclaw/.cache/   — PVC subPath, writable
#   ✅ /home/openclaw/.local/   — PVC subPath, writable
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
# Extract ACPX_PINNED_VERSION from config.ts and install that exact version
# so the runtime version check passes without triggering a re-install.
RUN cd /app/extensions/acpx \
    && PINNED=$(grep 'ACPX_PINNED_VERSION' src/config.ts | grep -o '"[^"]*"' | head -1 | tr -d '"') \
    && echo "Installing acpx@${PINNED} (from ACPX_PINNED_VERSION)" \
    && npm install --omit=dev --no-save "acpx@${PINNED}" 2>&1 \
    && /app/extensions/acpx/node_modules/.bin/acpx --version

# ── Make acpx available globally via PATH ──
# Sub-agents use `exec acpx ...` from workspace dir; need acpx on PATH.
ENV PATH="/app/extensions/acpx/node_modules/.bin:${PATH}"

# ── Kiro config (image layer, read-only but readable at runtime) ──
# Note: /home/openclaw/.kiro/ is read-only at runtime. The kiro-cli ACP mode
# needs to write to ~/.kiro/sessions/. The init container copies this config
# to the PVC at /home/openclaw/.openclaw/.kiro/ which IS writable.
# A wrapper script redirects HOME so kiro-cli uses the PVC copy.
RUN mkdir -p /opt/openclaw-custom/.kiro/agents /opt/openclaw-custom/.kiro/settings
COPY kiro-agent-config.json /opt/openclaw-custom/.kiro/agents/kiro_default.json
RUN echo '{"chat.defaultAgent": "kiro_default"}' > /opt/openclaw-custom/.kiro/settings/cli.json \
    && chown -R 1000:1000 /opt/openclaw-custom/.kiro

# ── acpx symlink: ~/.acpx → ~/.openclaw/.acpx (PVC, writable) ──
RUN mkdir -p /home/openclaw \
    && ln -sf /home/openclaw/.openclaw/.acpx /home/openclaw/.acpx \
    && chown -h 1000:1000 /home/openclaw/.acpx

# ── Staging area for PVC content (copied by init container) ──
RUN mkdir -p /opt/openclaw-custom/skills
COPY skills/search /opt/openclaw-custom/skills/search
COPY KIRO-PLAYBOOK.md /opt/openclaw-custom/KIRO-PLAYBOOK.md
COPY kiro-wrapper.sh /opt/openclaw-custom/.kiro-wrapper.sh
RUN chmod +x /opt/openclaw-custom/skills/search/scripts/search.sh \
    && chmod +x /opt/openclaw-custom/.kiro-wrapper.sh \
    && chown -R 1000:1000 /opt/openclaw-custom

# ── Entrypoint wrapper: background auto-pair (fallback) + exec openclaw ──
COPY entrypoint-wrapper.sh /usr/local/bin/entrypoint-wrapper.sh
RUN chmod +x /usr/local/bin/entrypoint-wrapper.sh

USER node

# ── Verify ──
RUN kiro-cli --version && jq --version \
    && /app/extensions/acpx/node_modules/.bin/acpx --version \
    && ls /opt/openclaw-custom/skills/search/SKILL.md \
    && ls /opt/openclaw-custom/KIRO-PLAYBOOK.md

LABEL org.opencontainers.image.title="openclaw-custom" \
      org.opencontainers.image.description="OpenClaw with Kiro CLI + Tavily Search" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"

# Keep base image entrypoint (docker-entrypoint.sh) and CMD (node openclaw.mjs gateway --allow-unconfigured).
# Do NOT override ENTRYPOINT here - it clears the base CMD.
