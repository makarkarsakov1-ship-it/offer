import logging
import os
from datetime import datetime, timezone

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS business_connections (
    connection_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    username TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 0,
    can_reply INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_connection_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    owner_username TEXT,
    recipient_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    nft_url TEXT NOT NULL,
    gift_name TEXT NOT NULL,
    gift_number TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected')),
    message_id INTEGER,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_pending_offer
    ON offers (chat_id, nft_url) WHERE status = 'pending';
"""

_db_path: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _connect() -> aiosqlite.Connection:
    return aiosqlite.connect(_db_path)


async def init_db(path: str) -> None:
    global _db_path
    _db_path = path
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    async with _connect() as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(SCHEMA)
        await conn.commit()
    log.info("database ready at %s", path)


async def upsert_connection(connection_id: str, user_id: int, username: str | None,
                            is_enabled: bool, can_reply: bool) -> None:
    async with _connect() as conn:
        await conn.execute(
            """
            INSERT INTO business_connections
                (connection_id, user_id, username, is_enabled, can_reply, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(connection_id) DO UPDATE SET
                user_id = excluded.user_id,
                username = excluded.username,
                is_enabled = excluded.is_enabled,
                can_reply = excluded.can_reply,
                updated_at = excluded.updated_at
            """,
            (connection_id, user_id, username, int(is_enabled), int(can_reply), _now()),
        )
        await conn.commit()


async def get_connection(connection_id: str) -> dict | None:
    async with _connect() as conn:
        conn.row_factory = _dict_factory
        cur = await conn.execute(
            "SELECT * FROM business_connections WHERE connection_id = ?", (connection_id,)
        )
        return await cur.fetchone()


async def create_offer(*, business_connection_id: str, owner_id: int, owner_username: str | None,
                       recipient_id: int, chat_id: int, nft_url: str, gift_name: str,
                       gift_number: str, amount: str, currency: str) -> int:
    """Insert a pending offer. Raises sqlite3.IntegrityError if one is already pending."""
    async with _connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO offers (business_connection_id, owner_id, owner_username, recipient_id,
                                chat_id, nft_url, gift_name, gift_number, amount, currency,
                                status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (business_connection_id, owner_id, owner_username, recipient_id, chat_id,
             nft_url, gift_name, gift_number, amount, currency, _now()),
        )
        await conn.commit()
        return cur.lastrowid


async def set_message_id(offer_id: int, message_id: int) -> None:
    async with _connect() as conn:
        await conn.execute("UPDATE offers SET message_id = ? WHERE id = ?", (message_id, offer_id))
        await conn.commit()


async def delete_offer(offer_id: int) -> None:
    async with _connect() as conn:
        await conn.execute("DELETE FROM offers WHERE id = ?", (offer_id,))
        await conn.commit()


async def get_offer(offer_id: int) -> dict | None:
    async with _connect() as conn:
        conn.row_factory = _dict_factory
        cur = await conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,))
        return await cur.fetchone()


async def transition(offer_id: int, new_status: str) -> bool:
    """Move a pending offer to accepted/rejected. Atomic: returns False if already decided."""
    async with _connect() as conn:
        cur = await conn.execute(
            "UPDATE offers SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
            (new_status, _now(), offer_id),
        )
        await conn.commit()
        return cur.rowcount == 1
