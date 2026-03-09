# Chromium Browser Sidecar

OpenClaw agents can optionally include a headless Chromium browser sidecar for web automation tasks (research, scraping, form filling, screenshots, etc).

## How It Works

When an agent is created with `enable_chromium: true`:

1. **CRD field**: `spec.chromium.enabled: true` is set on the `OpenClawInstance` CRD
2. **Operator injects sidecar**: The openclaw-operator auto-injects a `chromium` container (image: `ghcr.io/browserless/chromium:latest`) into the agent's StatefulSet
3. **CDP endpoint**: The chromium container exposes Chrome DevTools Protocol (CDP) on port `9222`
4. **Browser config**: We inject a `browserless` profile in `spec.config.raw` pointing to the CDP endpoint
5. **Agent uses browser**: The OpenClaw agent's `browser` tool automatically connects via the `browserless` profile

## Browser Profile Configuration

### What we write (`spec.config.raw`):

```json
{
  "browser": {
    "defaultProfile": "browserless",
    "remoteCdpTimeoutMs": 3000,
    "remoteCdpHandshakeTimeoutMs": 5000,
    "profiles": {
      "browserless": {
        "cdpUrl": "http://<agent-name>-0:9222",
        "color": "#4285F4"
      }
    }
  }
}
```

> **Important**: Use the pod hostname (`<agent-name>-0`) instead of `127.0.0.1`. OpenClaw treats loopback addresses as local and performs process ownership checks on the port — rejecting it because the sidecar is "not by openclaw". Using the pod hostname makes it a non-loopback address, so OpenClaw treats it as remote CDP and connects directly without ownership checks.

### What the operator auto-adds (merge):

```json
{
  "browser": {
    "profiles": {
      "chrome": {
        "attachOnly": true,
        "cdpUrl": "${OPENCLAW_CHROMIUM_CDP}",
        "color": "#4285F4"
      },
      "default": {
        "attachOnly": true,
        "cdpUrl": "${OPENCLAW_CHROMIUM_CDP}",
        "color": "#4285F4"
      }
    }
  }
}
```

### Final merged result (3 profiles):

| Profile | Source | Default? | Mode | Usable? |
|---------|--------|----------|------|---------|
| `browserless` | Our config | ✅ Yes | Remote CDP (direct connect) | ✅ Yes |
| `chrome` | Operator | No | `attachOnly` (extension relay) | ❌ No (no user to attach) |
| `default` | Operator | No | `attachOnly` (extension relay) | ❌ No (no user to attach) |

The agent calls the `browser` tool without specifying a profile → uses `defaultProfile` → `browserless` → works.

## Important: Profile Naming

**Do NOT use `openclaw` as the profile name.** The `openclaw` profile is reserved for OpenClaw-managed local browsers. If used:
- OpenClaw tries to launch its own browser
- Finds port 9222 occupied by the sidecar
- Reports: `Port 9222 is in use for profile "openclaw" but not by openclaw`
- Browser becomes unusable

We use `browserless` instead, which OpenClaw treats as a remote CDP profile (no launch attempt).

## Important: Config mergeMode

When patching an existing agent's CRD `spec.config.raw`, be aware of `mergeMode`:

- **`merge` (default)**: Deep-merges CRD config with PVC config. Old keys on PVC are **preserved** even if removed from CRD. Useful for preserving runtime changes.
- **`overwrite`**: Replaces PVC config entirely from CRD on each restart. Needed when cleaning up stale profile entries.

If switching an existing agent's browser config, temporarily set `mergeMode: "overwrite"` to flush stale PVC data, then optionally revert to `merge`.

## Resource Impact

Enabling Chromium adds to the agent pod:
- **CPU**: +500m request / +500m limit
- **Memory**: +1Gi request / +1Gi limit
- **Total per-agent pod with Chromium**: ~1.7 vCPU limit, ~3.2Gi memory limit (4 containers)

## China Region (cn-northwest-1)

`ghcr.io` is inaccessible from China. The Chromium image must be:
1. Pulled locally: `docker pull ghcr.io/browserless/chromium:latest`
2. Saved as tar: `docker save -o chromium.tar ...`
3. Uploaded to CN S3 bucket
4. Imported on each CN node via privileged DaemonSet (`ctr -n k8s.io images import`)
5. Tagged to match operator expectation: `ctr -n k8s.io images tag <cn-ecr-ref> ghcr.io/browserless/chromium:latest`

**Note**: This must be re-done after CN node replacement.

## API

### Create Agent with Chromium

```bash
POST /api/v1/tenants/{tenant}/agents
{
  "name": "my-agent",
  "llm_provider": "bedrock",
  "llm_model": "...",
  "enable_chromium": true,
  ...
}
```

### Enable Chromium on Existing Agent

```bash
# Via kubectl (direct CRD patch)
kubectl patch openclawinstance <agent-name> -n tenant-<tenant> \
  --type merge -p '{
    "spec": {
      "chromium": {"enabled": true},
      "config": {
        "raw": {
          "browser": {
            "defaultProfile": "browserless",
            "profiles": {
              "browserless": {
                "cdpUrl": "http://127.0.0.1:9222",
                "color": "#4285F4"
              }
            }
          }
        }
      }
    }
  }'
```

## Files Modified

| File | Change |
|------|--------|
| `api/models/agent.py` | Added `enable_chromium: bool = Field(default=False)` to `AgentCreate` |
| `api/routers/agents.py` | Passes `enable_chromium` to `k8s_client.create_openclaw_instance()` |
| `api/services/k8s_client.py` | Sets `spec.chromium.enabled` in CRD body; injects `browser.browserless` profile in `spec.config.raw` when `enable_chromium=True` |
| `web-console/src/api.js` | `createAgent()` passes `enable_chromium` parameter |
| `web-console/src/App.jsx` | Checkbox toggle in CreateAgentModal with resource cost note |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Port 9222 is in use but not by openclaw` | cdpUrl uses `127.0.0.1` (loopback) | Change to `http://<agent-name>-0:9222` (pod hostname) |
| `attachOnly is enabled and CDP websocket not reachable` | Agent using `chrome`/`default` profile | Ensure `defaultProfile: "browserless"` |
| Old profile stuck in config | `mergeMode: "merge"` preserves PVC data | Switch to `overwrite` temporarily |
| Chromium pod `ImagePullBackOff` (CN) | ghcr.io blocked in China | Re-import image via S3 + DaemonSet |
| Chromium pod `ImagePullBackOff` (CN after node replacement) | New node missing image | Re-run DaemonSet import + tag |
