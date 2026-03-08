"""Usage aggregator - rolls up events into hourly and daily summaries."""
import os
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func, and_, text
try:
    from billing.models import UsageEvent, HourlyUsage, DailyUsage
except ImportError:
    from models import UsageEvent, HourlyUsage, DailyUsage, Base


class Config:
    """Configuration from environment variables."""

    DATABASE_URL = os.getenv("DATABASE_URL", "")
    AGGREGATION_INTERVAL = int(os.getenv("AGGREGATION_INTERVAL", "300"))  # 5 minutes


# Model pricing per million tokens (approximate)
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
    # Add Bedrock variants
    "global.anthropic.claude-opus-4-6-v1": {"input": 15.0, "output": 75.0},
    "global.anthropic.claude-sonnet-4-6-v1": {"input": 3.0, "output": 15.0},
    "us.anthropic.claude-haiku-4-5-20251001-v1": {"input": 0.8, "output": 4.0},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost based on token usage."""
    # Try exact match first
    pricing = MODEL_PRICING.get(model)

    # If no exact match, try to find by base model name
    if not pricing:
        for model_key in MODEL_PRICING:
            if model_key in model or model in model_key:
                pricing = MODEL_PRICING[model_key]
                break

    # Default fallback pricing (use Sonnet pricing)
    if not pricing:
        pricing = {"input": 3.0, "output": 15.0}

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return round(input_cost + output_cost, 6)


class UsageAggregator:
    """Aggregate usage events into hourly and daily summaries."""

    def __init__(self):
        self.engine = create_async_engine(
            Config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
            echo=False,
        )
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self):
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def aggregate_hourly(self, start_time: datetime, end_time: datetime):
        """Aggregate events into hourly buckets."""
        async with self.async_session() as session:
            # Query events grouped by hour
            result = await session.execute(
                select(
                    UsageEvent.tenant,
                    UsageEvent.agent,
                    UsageEvent.model,
                    UsageEvent.provider,
                    func.date_trunc(
                        "hour", func.to_timestamp(UsageEvent.timestamp / 1000)
                    ).label("hour"),
                    func.sum(UsageEvent.input_tokens).label("input_tokens"),
                    func.sum(UsageEvent.output_tokens).label("output_tokens"),
                    func.sum(UsageEvent.cache_read).label("cache_read"),
                    func.sum(UsageEvent.cache_write).label("cache_write"),
                    func.sum(UsageEvent.total_tokens).label("total_tokens"),
                    func.count().label("call_count"),
                )
                .where(
                    and_(
                        UsageEvent.timestamp >= int(start_time.timestamp() * 1000),
                        UsageEvent.timestamp < int(end_time.timestamp() * 1000),
                    )
                )
                .group_by(
                    UsageEvent.tenant,
                    UsageEvent.agent,
                    UsageEvent.model,
                    UsageEvent.provider,
                    "hour",
                )
            )

            for row in result:
                # Calculate cost
                cost = calculate_cost(row.model, row.input_tokens, row.output_tokens)

                # Strip timezone from date_trunc result (DB column is naive)
                hour_naive = row.hour.replace(tzinfo=None) if row.hour and row.hour.tzinfo else row.hour

                # Upsert hourly usage
                existing = await session.execute(
                    select(HourlyUsage).where(
                        and_(
                            HourlyUsage.tenant == row.tenant,
                            HourlyUsage.agent == row.agent,
                            HourlyUsage.model == row.model,
                            HourlyUsage.provider == row.provider,
                            HourlyUsage.hour == hour_naive,
                        )
                    )
                )
                hourly = existing.scalar_one_or_none()

                if hourly:
                    # Update existing
                    hourly.input_tokens = row.input_tokens
                    hourly.output_tokens = row.output_tokens
                    hourly.cache_read = row.cache_read
                    hourly.cache_write = row.cache_write
                    hourly.total_tokens = row.total_tokens
                    hourly.call_count = row.call_count
                    hourly.estimated_cost = cost
                    hourly.updated_at = datetime.utcnow()
                else:
                    # Create new
                    hourly = HourlyUsage(
                        tenant=row.tenant,
                        agent=row.agent,
                        model=row.model,
                        provider=row.provider,
                        hour=hour_naive,
                        input_tokens=row.input_tokens,
                        output_tokens=row.output_tokens,
                        cache_read=row.cache_read,
                        cache_write=row.cache_write,
                        total_tokens=row.total_tokens,
                        call_count=row.call_count,
                        estimated_cost=cost,
                    )
                    session.add(hourly)

            await session.commit()
            print(f"Aggregated hourly usage for {start_time} to {end_time}")

    async def aggregate_daily(self, start_time: datetime, end_time: datetime):
        """Aggregate events into daily buckets."""
        async with self.async_session() as session:
            # Query events grouped by day
            result = await session.execute(
                select(
                    UsageEvent.tenant,
                    UsageEvent.agent,
                    UsageEvent.model,
                    UsageEvent.provider,
                    func.date_trunc(
                        "day", func.to_timestamp(UsageEvent.timestamp / 1000)
                    ).label("date"),
                    func.sum(UsageEvent.input_tokens).label("input_tokens"),
                    func.sum(UsageEvent.output_tokens).label("output_tokens"),
                    func.sum(UsageEvent.cache_read).label("cache_read"),
                    func.sum(UsageEvent.cache_write).label("cache_write"),
                    func.sum(UsageEvent.total_tokens).label("total_tokens"),
                    func.count().label("call_count"),
                )
                .where(
                    and_(
                        UsageEvent.timestamp >= int(start_time.timestamp() * 1000),
                        UsageEvent.timestamp < int(end_time.timestamp() * 1000),
                    )
                )
                .group_by(
                    UsageEvent.tenant,
                    UsageEvent.agent,
                    UsageEvent.model,
                    UsageEvent.provider,
                    "date",
                )
            )

            for row in result:
                # Calculate cost
                cost = calculate_cost(row.model, row.input_tokens, row.output_tokens)

                # Strip timezone from date_trunc result (DB column is naive)
                date_naive = row.date.replace(tzinfo=None) if row.date and row.date.tzinfo else row.date

                # Upsert daily usage
                existing = await session.execute(
                    select(DailyUsage).where(
                        and_(
                            DailyUsage.tenant == row.tenant,
                            DailyUsage.agent == row.agent,
                            DailyUsage.model == row.model,
                            DailyUsage.provider == row.provider,
                            DailyUsage.date == date_naive,
                        )
                    )
                )
                daily = existing.scalar_one_or_none()

                if daily:
                    # Update existing
                    daily.input_tokens = row.input_tokens
                    daily.output_tokens = row.output_tokens
                    daily.cache_read = row.cache_read
                    daily.cache_write = row.cache_write
                    daily.total_tokens = row.total_tokens
                    daily.call_count = row.call_count
                    daily.estimated_cost = cost
                    daily.updated_at = datetime.utcnow()
                else:
                    # Create new
                    daily = DailyUsage(
                        tenant=row.tenant,
                        agent=row.agent,
                        model=row.model,
                        provider=row.provider,
                        date=date_naive,
                        input_tokens=row.input_tokens,
                        output_tokens=row.output_tokens,
                        cache_read=row.cache_read,
                        cache_write=row.cache_write,
                        total_tokens=row.total_tokens,
                        call_count=row.call_count,
                        estimated_cost=cost,
                    )
                    session.add(daily)

            await session.commit()
            print(f"Aggregated daily usage for {start_time} to {end_time}")

    async def run(self):
        """Main aggregator loop."""
        print("Starting usage aggregator")
        print(f"Database: {Config.DATABASE_URL}")
        print(f"Aggregation interval: {Config.AGGREGATION_INTERVAL}s")

        # Initialize database
        await self.init_db()

        while True:
            try:
                # Aggregate last hour and last day
                now = datetime.utcnow()
                hour_ago = now - timedelta(hours=1)
                day_ago = now - timedelta(days=1)

                # Run both aggregations
                await self.aggregate_hourly(hour_ago, now)
                await self.aggregate_daily(day_ago, now)

            except Exception as e:
                print(f"Error in aggregator loop: {e}")

            # Wait before next aggregation
            await asyncio.sleep(Config.AGGREGATION_INTERVAL)


async def main():
    """Entry point."""
    if not Config.DATABASE_URL:
        print("Error: DATABASE_URL is required")
        return 1

    aggregator = UsageAggregator()
    await aggregator.run()


if __name__ == "__main__":
    asyncio.run(main())
