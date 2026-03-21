"""Add custom_image and custom_image_tag columns to agents table.

Run with: python -m api.migrations.add_custom_image_columns
"""
import asyncio

from sqlalchemy import text
from api.database import engine


async def migrate():
    async with engine.begin() as conn:
        # Check if columns already exist (SQLite compatible)
        result = await conn.execute(text("PRAGMA table_info(agents)"))
        columns = {row[1] for row in result.fetchall()}

        if "custom_image" not in columns:
            await conn.execute(text("ALTER TABLE agents ADD COLUMN custom_image VARCHAR(512)"))
            print("✅ Added column: custom_image")
        else:
            print("⏭️  Column custom_image already exists")

        if "custom_image_tag" not in columns:
            await conn.execute(text("ALTER TABLE agents ADD COLUMN custom_image_tag VARCHAR(128)"))
            print("✅ Added column: custom_image_tag")
        else:
            print("⏭️  Column custom_image_tag already exists")

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
