from __future__ import annotations

import aiosqlite
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from .config import DB_PATH


INIT_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    name TEXT,
    is_private INTEGER DEFAULT 0,
    created_ts INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT,
    real_name TEXT,
    display_name TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    ts TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    user_id TEXT,
    text TEXT,
    thread_ts TEXT,
    subtype TEXT,
    json TEXT NOT NULL,
    FOREIGN KEY(channel_id) REFERENCES channels(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, content='messages', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, text) VALUES('delete', old.rowid, old.text);
  INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    name TEXT,
    mimetype TEXT,
    size INTEGER,
    url_private TEXT,
    created_ts INTEGER,
    channel_id TEXT,
    user_id TEXT,
    title TEXT,
    json TEXT NOT NULL
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(INIT_SQL)
        await db.commit()


async def upsert_channel(db: aiosqlite.Connection, channel: Dict[str, Any]) -> None:
    await db.execute(
        """
        INSERT INTO channels (id, name, is_private, created_ts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name, is_private=excluded.is_private
        """,
        (
            channel.get("id"),
            channel.get("name") or channel.get("user") or "",
            1 if channel.get("is_private") else 0,
            channel.get("created") or 0,
        ),
    )


async def upsert_user(db: aiosqlite.Connection, user: Dict[str, Any]) -> None:
    profile = user.get("profile") or {}
    await db.execute(
        """
        INSERT INTO users (id, name, real_name, display_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name, real_name=excluded.real_name, display_name=excluded.display_name
        """,
        (
            user.get("id"),
            user.get("name"),
            user.get("real_name"),
            profile.get("display_name") or profile.get("real_name") or user.get("real_name"),
        ),
    )


async def insert_message(db: aiosqlite.Connection, message: Dict[str, Any], channel_id: str) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO messages (ts, channel_id, user_id, text, thread_ts, subtype, json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message.get("ts"),
            channel_id,
            message.get("user"),
            message.get("text", ""),
            message.get("thread_ts"),
            message.get("subtype"),
            __import__("json").dumps(message, ensure_ascii=False),
        ),
    )


async def insert_file(db: aiosqlite.Connection, file: Dict[str, Any], channel_id: Optional[str]) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO files (id, name, mimetype, size, url_private, created_ts, channel_id, user_id, title, json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file.get("id"),
            file.get("name"),
            file.get("mimetype"),
            file.get("size"),
            file.get("url_private"),
            file.get("created"),
            channel_id,
            file.get("user"),
            file.get("title"),
            __import__("json").dumps(file, ensure_ascii=False),
        ),
    )


async def search_messages(
    db: aiosqlite.Connection,
    query: str,
    channel_id: Optional[str] = None,
    user_id: Optional[str] = None,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    where = ["m.rowid = messages_fts.rowid"]
    params: List[Any] = []
    if query:
        where.append("messages_fts MATCH ?")
        params.append(query)
    if channel_id:
        where.append("m.channel_id = ?")
        params.append(channel_id)
    if user_id:
        where.append("m.user_id = ?")
        params.append(user_id)
    if start_ts:
        where.append("m.ts >= ?")
        params.append(start_ts)
    if end_ts:
        where.append("m.ts <= ?")
        params.append(end_ts)

    sql = f"""
    SELECT m.*, c.name AS channel_name, u.display_name AS user_display
    FROM messages m JOIN messages_fts ON { ' AND '.join(where) }
    LEFT JOIN channels c ON m.channel_id = c.id
    LEFT JOIN users u ON m.user_id = u.id
    ORDER BY m.ts DESC
    LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cur = await db.execute(sql, params)
    rows = await cur.fetchall()
    return [dict(row) for row in rows]

