"""SQS pusher for usage events."""
import json
import time
from typing import List, Dict
import boto3
from config import Config


class SQSPusher:
    """Push usage events to SQS queue."""

    def __init__(self):
        self.sqs = boto3.client("sqs", region_name=Config.AWS_DEFAULT_REGION)
        self.queue_url = Config.SQS_QUEUE_URL
        self.batch = []
        self.batch_size = 10  # SQS SendMessageBatch max

    def push_event(self, event: Dict):
        """Add event to batch and flush if batch is full."""
        self.batch.append(event)

        if len(self.batch) >= self.batch_size:
            self.flush()

    def flush(self):
        """Send all batched events to SQS."""
        if not self.batch:
            return

        try:
            entries = [
                {
                    "Id": str(i),
                    "MessageBody": json.dumps(event),
                }
                for i, event in enumerate(self.batch)
            ]

            response = self.sqs.send_message_batch(
                QueueUrl=self.queue_url, Entries=entries
            )

            # Check for failures
            if "Failed" in response and response["Failed"]:
                print(f"Failed to send {len(response['Failed'])} messages:")
                for failed in response["Failed"]:
                    print(f"  - ID {failed['Id']}: {failed['Message']}")

            # Clear batch after sending
            self.batch = []

        except Exception as e:
            print(f"Error sending batch to SQS: {e}")
            # Don't clear batch on error - will retry next flush

    def create_usage_event(
        self,
        tenant: str,
        agent: str,
        model: str,
        provider: str,
        usage: Dict,
        timestamp: int,
    ) -> Dict:
        """Create a usage event from message data."""
        return {
            "tenant": tenant,
            "agent": agent,
            "model": model,
            "provider": provider,
            "input_tokens": usage.get("input", 0),
            "output_tokens": usage.get("output", 0),
            "cache_read": usage.get("cacheRead", 0),
            "cache_write": usage.get("cacheWrite", 0),
            "total_tokens": usage.get("totalTokens", 0),
            "timestamp": timestamp,
        }

    def __del__(self):
        """Flush any remaining events on destruction."""
        self.flush()
