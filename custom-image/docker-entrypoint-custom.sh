#!/bin/sh
set -e

# Fix home directory permissions for acpx/kiro-cli.
# The k8s-operator creates /home/openclaw owned by root for the PVC mount point.
# Tools like acpx need to write ~/.acpx — we create dirs under the writable PVC
# and symlink from HOME.
HOME_DIR="${HOME:-/home/openclaw}"
OPENCLAW_DIR="$HOME_DIR/.openclaw"

if [ -d "$OPENCLAW_DIR" ]; then
    # Create tool dirs under PVC (always writable by node)
    for dir in .acpx .cache .local .config; do
        mkdir -p "$OPENCLAW_DIR/$dir" 2>/dev/null || true
    done

    # Try to symlink from HOME (may fail if HOME dir is root-owned, that's OK)
    for dir in .acpx .cache .local .config; do
        if [ ! -e "$HOME_DIR/$dir" ]; then
            ln -sf "$OPENCLAW_DIR/$dir" "$HOME_DIR/$dir" 2>/dev/null || true
        fi
    done
fi

# Fallback: if symlinks failed (permission denied on HOME), set env vars
# so acpx can find its data via XDG paths
if [ ! -d "$HOME_DIR/.acpx" ] && [ -d "$OPENCLAW_DIR/.acpx" ]; then
    # Override HOME to PVC path for acpx subprocess calls
    export ACPX_SESSION_DIR="$OPENCLAW_DIR/.acpx/sessions"
    mkdir -p "$ACPX_SESSION_DIR" 2>/dev/null || true
fi

# Fall through to original entrypoint logic
if [ "${1#-}" != "${1}" ] || [ -z "$(command -v "${1}")" ] || { [ -f "${1}" ] && ! [ -x "${1}" ]; }; then
    set -- node "$@"
fi

exec "$@"
