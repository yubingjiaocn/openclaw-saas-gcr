"""Prometheus metrics for OpenClaw usage tracking."""
from prometheus_client import Counter, start_http_server


# Token usage counters
tokens_total = Counter(
    "openclaw_tokens_total",
    "Total tokens used by OpenClaw agents",
    ["tenant", "agent", "model", "provider", "type"],
)

# LLM call counter
llm_calls_total = Counter(
    "openclaw_llm_calls_total",
    "Total LLM API calls made by OpenClaw agents",
    ["tenant", "agent", "model", "provider"],
)

# Session counter
sessions_total = Counter(
    "openclaw_sessions_total",
    "Total unique sessions tracked",
    ["tenant", "agent"],
)


def record_usage(tenant: str, agent: str, model: str, provider: str, usage: dict):
    """Record token usage from a message."""
    # Record token counts by type
    if usage.get("input"):
        tokens_total.labels(
            tenant=tenant, agent=agent, model=model, provider=provider, type="input"
        ).inc(usage["input"])

    if usage.get("output"):
        tokens_total.labels(
            tenant=tenant, agent=agent, model=model, provider=provider, type="output"
        ).inc(usage["output"])

    if usage.get("cacheRead"):
        tokens_total.labels(
            tenant=tenant,
            agent=agent,
            model=model,
            provider=provider,
            type="cache_read",
        ).inc(usage["cacheRead"])

    if usage.get("cacheWrite"):
        tokens_total.labels(
            tenant=tenant,
            agent=agent,
            model=model,
            provider=provider,
            type="cache_write",
        ).inc(usage["cacheWrite"])

    # Record LLM call
    llm_calls_total.labels(
        tenant=tenant, agent=agent, model=model, provider=provider
    ).inc()


def record_session(tenant: str, agent: str):
    """Record a new session."""
    sessions_total.labels(tenant=tenant, agent=agent).inc()


def start_metrics_server(port: int):
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)
    print(f"Prometheus metrics server started on port {port}")
