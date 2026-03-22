#!/bin/bash
# Wrapper entrypoint: background auto-pair + exec openclaw
# Solves the race condition where gateway generates identity after startup
# but clients connect before self-pairing completes.

auto_pair() {
  local home="${HOME:-/home/openclaw}"
  local data="$home/.openclaw"
  local id_file="$data/identity/device.json"
  local paired_file="$data/devices/paired.json"

  # Wait for gateway to generate identity (up to 60s)
  for i in $(seq 1 60); do
    [ -f "$id_file" ] && break
    sleep 1
  done

  [ ! -f "$id_file" ] && return 1

  # If paired.json already has a matching entry, skip
  if [ -f "$paired_file" ]; then
    local dev_id
    dev_id=$(node -e "console.log(JSON.parse(require('fs').readFileSync('$id_file')).deviceId)")
    local has_match
    has_match=$(node -e "
      const p=JSON.parse(require('fs').readFileSync('$paired_file'));
      console.log(p['$dev_id'] ? 'yes' : 'no');
    " 2>/dev/null)
    [ "$has_match" = "yes" ] && return 0
  fi

  # Register device identity into paired.json
  node -e "
    const fs = require('fs');
    const dev = JSON.parse(fs.readFileSync('$id_file'));
    const pk = dev.publicKeyPem.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
    const paired = {};
    paired[dev.deviceId] = {
      deviceId: dev.deviceId,
      publicKey: pk,
      platform: 'linux',
      clientId: 'gateway-client',
      clientMode: 'backend',
      role: 'operator',
      roles: ['operator'],
      scopes: ['operator.admin','operator.read','operator.write','operator.approvals','operator.pairing'],
      pairedAt: Date.now()
    };
    fs.mkdirSync('$data/devices', { recursive: true });
    fs.writeFileSync('$paired_file', JSON.stringify(paired, null, 2));
  "
}

# Run auto-pair in background so openclaw starts immediately
auto_pair &

# Exec into the original entrypoint (docker-entrypoint.sh from base image)
exec docker-entrypoint.sh "$@"
