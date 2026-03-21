"""Application configuration"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # JWT Authentication
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # Kubernetes
    K8S_IN_CLUSTER: bool = False

    # Admin seed (set via env or K8s secret)
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    # Logging
    LOG_LEVEL: str = "INFO"

    # AWS Region settings (parameterized for multi-region support)
    AWS_REGION: str = os.getenv("AWS_REGION", "us-west-2")
    AWS_PARTITION: str = os.getenv("AWS_PARTITION", "aws")
    AWS_ACCOUNT_ID: str = os.getenv("AWS_ACCOUNT_ID", "956045422469")

    SQS_QUEUE_URL: str = os.getenv(
        "SQS_QUEUE_URL",
        "https://us-west-2.queue.amazonaws.com/956045422469/openclaw-saas-usage-events"
    )

    ECR_REGISTRY: str = os.getenv(
        "ECR_REGISTRY",
        "956045422469.dkr.ecr.us-west-2.amazonaws.com"
    )

    METRICS_EXPORTER_TAG: str = os.getenv("METRICS_EXPORTER_TAG", "v0.1.0")

    # Available channels for this region (comma-separated, empty = all)
    AVAILABLE_CHANNELS: str = os.getenv("AVAILABLE_CHANNELS", "")

    # Custom agent image (overrides default ghcr.io/openclaw/openclaw)
    # Set to use a custom-built image with pre-installed tools (kiro-cli, tavily, etc.)
    DEFAULT_AGENT_IMAGE: str = os.getenv("DEFAULT_AGENT_IMAGE", "")
    DEFAULT_AGENT_IMAGE_TAG: str = os.getenv("DEFAULT_AGENT_IMAGE_TAG", "latest")

    @property
    def ecr_domain(self) -> str:
        return self.ECR_REGISTRY

    @property
    def sqs_url(self) -> str:
        return self.SQS_QUEUE_URL

    @property
    def metrics_exporter_image(self) -> str:
        return f"{self.ECR_REGISTRY}/openclaw-metrics-exporter:{self.METRICS_EXPORTER_TAG}"


settings = Settings()
