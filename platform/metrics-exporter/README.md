# Metrics Exporter Sidecar

Injected into every Agent Pod. Reads OpenClaw session data and:
1. Exposes Prometheus /metrics on :9090
2. Pushes usage events to SQS for Billing

## Data Source

Shared volume with Agent container:
- `sessions.json` — session-level token totals
- `*.jsonl` — per-message LLM call details (model, provider, tokens)

## Metrics

| Name | Type | Labels |
|------|------|--------|
| `openclaw_tokens_input_total` | Counter | tenant, agent, model |
| `openclaw_tokens_output_total` | Counter | tenant, agent, model |
| `openclaw_llm_requests_total` | Counter | tenant, agent, model, provider |
| `openclaw_sessions_active` | Gauge | tenant, agent |
