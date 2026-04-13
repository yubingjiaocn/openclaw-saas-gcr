"""Metrics exporter: scrapes otel-collector Prometheus endpoint, computes deltas, pushes to SQS."""
import time
import urllib.request
from typing import Dict, Optional, Tuple
from config import Config
from sqs_pusher import SQSPusher


def parse_prometheus_text(text: str) -> Dict[Tuple[str, str], float]:
    """Parse Prometheus text format into {(metric_name, label_key): value}.

    For openclaw_tokens_total{openclaw_token="input"} → key = ("openclaw_tokens_total", "input")
    For openclaw_message_processed_total{...} → key = ("openclaw_message_processed_total", "")
    For openclaw_cost_usd_total{...} → key = ("openclaw_cost_usd_total", "")
    """
    metrics: Dict[Tuple[str, str], float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parts = line.split()
            if len(parts) < 2:
                continue
            name_with_labels = parts[0]
            value = float(parts[1])

            # Extract base name and labels
            if "{" in name_with_labels:
                name = name_with_labels[: name_with_labels.index("{")]
                label_str = name_with_labels[name_with_labels.index("{") + 1 : name_with_labels.index("}")]
            else:
                name = name_with_labels
                label_str = ""

            # Skip histograms (bucket/sum/count) — we only want counters/gauges
            if name.endswith("_bucket") or name.endswith("_sum") or name.endswith("_count"):
                if "openclaw_tokens" not in name and "openclaw_cost" not in name:
                    continue

            # Parse openclaw_token label for token metrics
            token_type = ""
            if name in ("openclaw_tokens_total", "openclaw_tokens"):
                for part in label_str.split(","):
                    if "openclaw_token=" in part:
                        token_type = part.split("=", 1)[1].strip().strip('"')
                        break

            key = (name, token_type)
            metrics[key] = metrics.get(key, 0.0) + value
        except (ValueError, IndexError):
            continue
    return metrics


def extract_labels(text: str) -> Dict[str, str]:
    """Extract model/provider labels from any openclaw_tokens line."""
    for line in text.splitlines():
        if "openclaw_tokens" in line and "{" in line and not line.startswith("#"):
            label_str = line[line.index("{") + 1 : line.index("}")]
            labels = {}
            for part in label_str.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    labels[k.strip()] = v.strip().strip('"')
            return labels
    return {}


class MetricsExporter:
    """Scrape otel-collector /metrics, compute deltas, push to SQS."""

    def __init__(self):
        self.sqs_pusher = SQSPusher()
        self.prev_values: Dict[Tuple[str, str], float] = {}
        self.metrics_url = f"http://localhost:{Config.OTEL_METRICS_PORT}/metrics"

    def scrape(self) -> Optional[str]:
        """Fetch Prometheus metrics from otel-collector."""
        try:
            resp = urllib.request.urlopen(self.metrics_url, timeout=5)
            return resp.read().decode()
        except Exception as e:
            print(f"Scrape error: {e}")
            return None

    def compute_and_push(self, raw_text: str):
        """Compute deltas from previous scrape and push non-zero deltas to SQS."""
        current = parse_prometheus_text(raw_text)
        labels = extract_labels(raw_text)

        if not current:
            return

        # Compute deltas
        deltas: Dict[Tuple[str, str], float] = {}
        for key, value in current.items():
            prev = self.prev_values.get(key, 0.0)
            delta = value - prev
            if delta > 0:
                deltas[key] = delta

        # Update previous values
        self.prev_values = current

        if not deltas:
            return

        # Helper to get delta by metric name + optional token type
        def get_delta(metric_name: str, token_type: str = "") -> float:
            # Try with _total suffix
            for suffix in ["_total", ""]:
                key = (metric_name + suffix, token_type)
                if key in deltas:
                    return deltas[key]
            return 0.0

        input_tokens = get_delta("openclaw_tokens", "input")
        output_tokens = get_delta("openclaw_tokens", "output")
        cache_read = get_delta("openclaw_tokens", "cache_read")
        cache_write = get_delta("openclaw_tokens", "cache_write")
        total_tokens = get_delta("openclaw_tokens", "total")
        prompt_tokens = get_delta("openclaw_tokens", "prompt")
        cost_usd = get_delta("openclaw_cost_usd")
        messages = get_delta("openclaw_message_processed")

        if total_tokens == 0 and input_tokens == 0 and output_tokens == 0 and prompt_tokens == 0:
            return

        model = labels.get("openclaw_model", labels.get("model", "unknown"))
        provider = labels.get("openclaw_provider", labels.get("provider", "unknown"))

        event = {
            "tenant": Config.TENANT_NAME,
            "agent": Config.AGENT_NAME,
            "model": model,
            "provider": provider,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cache_read": int(cache_read),
            "cache_write": int(cache_write),
            "prompt_tokens": int(prompt_tokens),
            "total_tokens": int(total_tokens) or int(input_tokens + output_tokens),
            "cost_usd": round(cost_usd, 6),
            "messages": int(messages),
            "timestamp": int(time.time() * 1000),
        }

        self.sqs_pusher.push_event(event)
        print(f"Pushed usage: in={int(input_tokens)} out={int(output_tokens)} "
              f"cache_w={int(cache_write)} prompt={int(prompt_tokens)} "
              f"total={int(total_tokens)} cost=${cost_usd:.4f} msgs={int(messages)}")

    def run(self):
        """Main loop."""
        print(f"Starting metrics exporter for tenant={Config.TENANT_NAME}, agent={Config.AGENT_NAME}")
        print(f"Scraping otel-collector at {self.metrics_url}")
        print(f"Scrape interval: {Config.SCAN_INTERVAL_SECONDS}s")

        # Wait for otel-collector to be ready
        for attempt in range(10):
            raw = self.scrape()
            if raw is not None:
                print("otel-collector reachable")
                break
            print(f"Waiting for otel-collector... ({attempt + 1}/10)")
            time.sleep(5)
        else:
            print("WARNING: otel-collector not reachable after 50s, continuing anyway")

        while True:
            try:
                raw = self.scrape()
                if raw is not None:
                    self.compute_and_push(raw)
                self.sqs_pusher.flush()
            except Exception as e:
                print(f"Error in main loop: {e}")

            time.sleep(Config.SCAN_INTERVAL_SECONDS)


def main():
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return 1
    MetricsExporter().run()


if __name__ == "__main__":
    main()
