"""Migration script to add usage tracking tables."""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy.ext.asyncio import create_async_engine
from api.config import settings

# Import the usage models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../billing")))
from models import Base, UsageEvent, HourlyUsage, DailyUsage  # noqa: E402


async def run_migration():
    """Create usage tables."""
    print("Running migration: add_usage_tables")
    print(f"Database URL: {settings.DATABASE_URL}")

    engine = create_async_engine(settings.DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        # Create all tables defined in the billing models
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Migration completed successfully")


if __name__ == "__main__":
    asyncio.run(run_migration())
