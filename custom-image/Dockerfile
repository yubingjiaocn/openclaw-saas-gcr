# OpenClaw Custom Image with Kiro CLI + acpx + Tavily Search
# Base: official OpenClaw image (Debian bookworm, Node 24, Python 3.11)
# Target: linux/arm64 (Graviton)
FROM ghcr.io/openclaw/openclaw:latest

# ── System deps (as root) ──
USER root

# jq is needed by tavily-search skill script; xz/tar/curl already present
RUN apt-get update && apt-get install -y --no-install-recommends \
        jq \
    && rm -rf /var/lib/apt/lists/*

# ── Kiro CLI (native binary, headless, aarch64) ──
# Download pinned version; place in /usr/local/bin so it's on PATH for all users
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

# ── acpx (global install, provides `acpx` CLI) ──
RUN npm install -g acpx@latest \
    && acpx --version

# ── Back to non-root user ──
# OpenClaw base image runs as 'node' (uid 1000)
USER node

# Verify tools are accessible
RUN kiro-cli --version && acpx --version && jq --version

# ── Labels ──
LABEL org.opencontainers.image.title="openclaw-custom" \
      org.opencontainers.image.description="OpenClaw with Kiro CLI + acpx + Tavily Search support" \
      org.opencontainers.image.source="https://github.com/chenxqdu/openclaw-saas-gcr"
