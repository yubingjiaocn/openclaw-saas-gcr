"""Main metrics exporter that scans OpenClaw JSONL session files."""
import json
import os
import time
import glob
from pathlib import Path
from typing import Dict, Set
from config import Config
from prometheus_metrics import (
    record_usage,
    record_session,
    start_metrics_server,
)
from sqs_pusher import SQSPusher


class MetricsExporter:
    """Scan JSONL files and export metrics."""

    def __init__(self):
        self.config = Config
        self.sqs_pusher = SQSPusher()
        self.state = self._load_state()
        self.tracked_sessions: Set[str] = set()

    def _load_state(self) -> Dict:
        """Load file positions from state file."""
        if os.path.exists(Config.STATE_FILE):
            try:
                with open(Config.STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state file: {e}")
                return {}
        return {}

    def _save_state(self):
        """Save file positions to state file."""
        try:
            with open(Config.STATE_FILE, "w") as f:
                json.dump(self.state, f)
        except Exception as e:
            print(f"Error saving state file: {e}")

    def _find_session_files(self) -> list:
        """Find all JSONL session files."""
        sessions_pattern = os.path.join(
            Config.DATA_DIR, "agents", "*", "sessions", "*.jsonl"
        )
        return glob.glob(sessions_pattern)

    def _process_file(self, file_path: str):
        """Process a single JSONL file incrementally."""
        # Get last known position for this file
        last_position = self.state.get(file_path, 0)

        try:
            with open(file_path, "r") as f:
                # Seek to last known position
                f.seek(last_position)

                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        self._process_record(record, file_path)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON in {file_path}: {e}")
                        continue

                # Save current position
                self.state[file_path] = f.tell()

        except FileNotFoundError:
            # File was deleted - remove from state
            if file_path in self.state:
                del self.state[file_path]
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")

    def _process_record(self, record: Dict, file_path: str):
        """Process a single JSONL record."""
        if record.get("type") != "message":
            return

        message = record.get("message", {})
        if message.get("role") != "assistant":
            return

        # Check if this is an LLM call with usage data
        usage = message.get("usage")
        if not usage:
            return

        model = message.get("model", "unknown")
        provider = message.get("provider", "unknown")
        timestamp = message.get("timestamp", int(time.time() * 1000))

        # Record Prometheus metrics
        record_usage(
            tenant=Config.TENANT_NAME,
            agent=Config.AGENT_NAME,
            model=model,
            provider=provider,
            usage=usage,
        )

        # Create and push SQS event
        event = self.sqs_pusher.create_usage_event(
            tenant=Config.TENANT_NAME,
            agent=Config.AGENT_NAME,
            model=model,
            provider=provider,
            usage=usage,
            timestamp=timestamp,
        )
        self.sqs_pusher.push_event(event)

        # Track session (based on file path)
        if file_path not in self.tracked_sessions:
            self.tracked_sessions.add(file_path)
            record_session(Config.TENANT_NAME, Config.AGENT_NAME)

    def run(self):
        """Main loop - scan files periodically."""
        print(
            f"Starting metrics exporter for tenant={Config.TENANT_NAME}, agent={Config.AGENT_NAME}"
        )
        print(f"Scanning directory: {Config.DATA_DIR}")
        print(f"Scan interval: {Config.SCAN_INTERVAL_SECONDS}s")

        # Start Prometheus metrics server
        start_metrics_server(Config.METRICS_PORT)

        while True:
            try:
                # Find and process all session files
                session_files = self._find_session_files()
                print(f"Found {len(session_files)} session files")

                for file_path in session_files:
                    self._process_file(file_path)

                # Flush any pending SQS messages
                self.sqs_pusher.flush()

                # Save state
                self._save_state()

            except Exception as e:
                print(f"Error in main loop: {e}")

            # Wait before next scan
            time.sleep(Config.SCAN_INTERVAL_SECONDS)


def main():
    """Entry point."""
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return 1

    exporter = MetricsExporter()
    exporter.run()


if __name__ == "__main__":
    main()
