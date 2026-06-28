"""
Control Plane — DB layer (asyncpg / PostgreSQL)
"""
import asyncpg
import os
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/snapevent"),
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db():
    """Create tables if they don't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS organisers (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email       TEXT UNIQUE NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS auth_tokens (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organiser_id UUID NOT NULL REFERENCES organisers(id) ON DELETE CASCADE,
                token        TEXT UNIQUE NOT NULL,
                expires_at   TIMESTAMPTZ NOT NULL,
                used         BOOLEAN DEFAULT FALSE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organiser_id UUID NOT NULL REFERENCES organisers(id) ON DELETE CASCADE,
                token        TEXT UNIQUE NOT NULL,
                expires_at   TIMESTAMPTZ NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_registry (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organiser_id UUID NOT NULL REFERENCES organisers(id) ON DELETE CASCADE,
                event_code   TEXT UNIQUE NOT NULL,
                event_name   TEXT NOT NULL,
                description  TEXT,
                event_date   DATE,
                status       TEXT DEFAULT 'STARTING',
                task_arn     TEXT,
                internal_url TEXT,
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                expires_at   TIMESTAMPTZ
            );
        """)
