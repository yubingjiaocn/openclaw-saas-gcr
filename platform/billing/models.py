"""SQLAlchemy models for usage tracking and billing."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Index, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UsageEvent(Base):
    """Raw usage events from SQS queue."""

    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant = Column(String(255), nullable=False, index=True)
    agent = Column(String(255), nullable=False, index=True)
    model = Column(String(255), nullable=False)
    provider = Column(String(255), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read = Column(Integer, default=0)
    cache_write = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    timestamp = Column(BigInteger, nullable=False)  # Unix timestamp in milliseconds
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_usage_events_tenant_timestamp", "tenant", "timestamp"),
        Index("idx_usage_events_created", "created_at"),
    )


class HourlyUsage(Base):
    """Aggregated usage by hour."""

    __tablename__ = "hourly_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant = Column(String(255), nullable=False, index=True)
    agent = Column(String(255), nullable=False, index=True)
    model = Column(String(255), nullable=False)
    provider = Column(String(255), nullable=False)
    hour = Column(DateTime, nullable=False)  # Hour bucket (e.g., 2026-03-07 15:00:00)
    input_tokens = Column(BigInteger, default=0)
    output_tokens = Column(BigInteger, default=0)
    cache_read = Column(BigInteger, default=0)
    cache_write = Column(BigInteger, default=0)
    total_tokens = Column(BigInteger, default=0)
    call_count = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index(
            "idx_hourly_usage_unique",
            "tenant",
            "agent",
            "model",
            "provider",
            "hour",
            unique=True,
        ),
        Index("idx_hourly_usage_tenant_hour", "tenant", "hour"),
    )


class DailyUsage(Base):
    """Aggregated usage by day."""

    __tablename__ = "daily_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant = Column(String(255), nullable=False, index=True)
    agent = Column(String(255), nullable=False, index=True)
    model = Column(String(255), nullable=False)
    provider = Column(String(255), nullable=False)
    date = Column(DateTime, nullable=False)  # Date bucket (e.g., 2026-03-07 00:00:00)
    input_tokens = Column(BigInteger, default=0)
    output_tokens = Column(BigInteger, default=0)
    cache_read = Column(BigInteger, default=0)
    cache_write = Column(BigInteger, default=0)
    total_tokens = Column(BigInteger, default=0)
    call_count = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index(
            "idx_daily_usage_unique",
            "tenant",
            "agent",
            "model",
            "provider",
            "date",
            unique=True,
        ),
        Index("idx_daily_usage_tenant_date", "tenant", "date"),
    )
