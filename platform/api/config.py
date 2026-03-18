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

    # Agent image settings (override for CN region or custom registries)
    # Default: ghcr.io (works globally). Set ECR_REGISTRY for CN or private registries.
    OPENCLAW_IMAGE_REPO: str = os.getenv("OPENCLAW_IMAGE_REPO", "")  # e.g. "735091234506.dkr.ecr.cn-northwest-1.amazonaws.com.cn/openclaw"
    OPENCLAW_IMAGE_TAG: str = os.getenv("OPENCLAW_IMAGE_TAG", "latest")
    CHROMIUM_IMAGE_REPO: str = os.getenv("CHROMIUM_IMAGE_REPO", "")
    CHROMIUM_IMAGE_TAG: str = os.getenv("CHROMIUM_IMAGE_TAG", "latest")

    # Available channels for this region (comma-separated, empty = all)
    AVAILABLE_CHANNELS: str = os.getenv("AVAILABLE_CHANNELS", "")

    @property
    def openclaw_image_repository(self) -> str:
        """OpenClaw agent image repo. Falls back to ECR_REGISTRY/openclaw, then ghcr.io default."""
        if self.OPENCLAW_IMAGE_REPO:
            return self.OPENCLAW_IMAGE_REPO
        if self.ECR_REGISTRY and "ghcr.io" not in self.ECR_REGISTRY:
            return f"{self.ECR_REGISTRY}/openclaw"
        return ""  # empty = let operator use its default (ghcr.io/openclaw/openclaw)

    @property
    def chromium_image_repository(self) -> str:
        """Chromium sidecar image repo. Falls back to ECR_REGISTRY/chromium, then operator default."""
        if self.CHROMIUM_IMAGE_REPO:
            return self.CHROMIUM_IMAGE_REPO
        if self.ECR_REGISTRY and "ghcr.io" not in self.ECR_REGISTRY:
            return f"{self.ECR_REGISTRY}/chromium"
        return ""  # empty = let operator use its default

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
