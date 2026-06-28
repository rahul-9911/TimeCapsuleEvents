"""
Event Worker — SQLite DB layer (aiosqlite)
Each event container has its own isolated SQLite at /data/event.db
"""
import os
import aiosqlite
from typing import Optional

EVENT_CODE = os.getenv("EVENT_CODE", "UNKNOWN")
DB_PATH = os.path.join(os.getenv("EFS_MOUNT", "/data"), f"{EVENT_CODE}_event.db")

_conn: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = await aiosqlite.connect(DB_PATH)
        _conn.row_factory = aiosqlite.Row
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


async def close_db():
    global _conn
    if _conn:
        await _conn.close()
        _conn = None


async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS access_codes (
            id          TEXT PRIMARY KEY,
            code        TEXT UNIQUE NOT NULL,
            label       TEXT,
            permission  TEXT NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            revoked     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS photos (
            id            TEXT PRIMARY KEY,
            access_code_id TEXT NOT NULL,
            s3_key        TEXT NOT NULL,
            original_name TEXT,
            content_type  TEXT DEFAULT 'image/jpeg',
            uploaded_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (access_code_id) REFERENCES access_codes(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id              TEXT PRIMARY KEY,
            access_code_id  TEXT NOT NULL,
            action          TEXT NOT NULL,
            photo_id        TEXT,
            timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address      TEXT,
            FOREIGN KEY (access_code_id) REFERENCES access_codes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_photos_code    ON photos(access_code_id);
        CREATE INDEX IF NOT EXISTS idx_activity_code  ON activity_log(access_code_id);
        CREATE INDEX IF NOT EXISTS idx_activity_ts    ON activity_log(timestamp);
    """)
    await db.commit()
