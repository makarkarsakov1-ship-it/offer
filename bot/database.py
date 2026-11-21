import logging
import os
from datetime import datetime, timedelta, timezone

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

CREATE TABLE IF NOT EXISTS business_contacts (
    connection_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    chat_id INTEGER NOT NULL,
    last_incoming_at TEXT NOT NULL,
    PRIMARY KEY (connection_id, user_id),
    FOREIGN KEY (connection_id) REFERENCES business_connections(connection_id)
);

CREATE INDEX IF NOT EXISTS idx_contacts_username
    ON business_contacts (username COLLATE NOCASE);

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

DROP INDEX IF EXISTS uniq_pending_offer;
CREATE UNIQUE INDEX IF NOT EXISTS uniq_pending_business_offer
    ON offers (chat_id, nft_url)
    WHERE status = 'pending' AND business_connection_id != 'inline';
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
        await conn.execute("PRAGMA foreign_keys=ON")
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


async def record_business_contact(connection_id: str, user_id: int, username: str | None,
                                  chat_id: int) -> None:
    async with _connect() as conn:
        await conn.execute(
            """
            INSERT INTO business_contacts
                (connection_id, user_id, username, chat_id, last_incoming_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(connection_id, user_id) DO UPDATE SET
                username = excluded.username,
                chat_id = excluded.chat_id,
                last_incoming_at = excluded.last_incoming_at
            """,
            (connection_id, user_id, username, chat_id, _now()),
        )
        await conn.commit()


async def find_contact_for_owner(owner_id: int, identifier: str) -> dict | None:
    identifier = identifier.strip()
    async with _connect() as conn:
        conn.row_factory = _dict_factory
        if identifier.startswith("@"):
            cur = await conn.execute(
                """
                SELECT bc.*, c.user_id AS owner_id, c.username AS owner_username,
                       c.is_enabled, c.can_reply, c.connection_id
                FROM business_contacts bc
                JOIN business_connections c ON c.connection_id = bc.connection_id
                WHERE c.user_id = ? AND LOWER(COALESCE(bc.username, '')) = LOWER(?)
                  AND c.is_enabled = 1 AND c.can_reply = 1
                ORDER BY bc.last_incoming_at DESC LIMIT 1
                """,
                (owner_id, identifier[1:]),
            )
        elif identifier.isdigit():
            cur = await conn.execute(
                """
                SELECT bc.*, c.user_id AS owner_id, c.username AS owner_username,
                       c.is_enabled, c.can_reply, c.connection_id
                FROM business_contacts bc
                JOIN business_connections c ON c.connection_id = bc.connection_id
                WHERE c.user_id = ? AND bc.user_id = ?
                  AND c.is_enabled = 1 AND c.can_reply = 1
                ORDER BY bc.last_incoming_at DESC LIMIT 1
                """,
                (owner_id, int(identifier)),
            )
        else:
            return None
        contact = await cur.fetchone()

    if contact is None:
        return None

    try:
        last_incoming = datetime.fromisoformat(contact["last_incoming_at"])
        if last_incoming.tzinfo is None:
            last_incoming = last_incoming.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last_incoming > timedelta(hours=23, minutes=59):
            return None
    except (TypeError, ValueError):
        return None

    return contact


async def list_recent_contacts(owner_id: int, limit: int = 20) -> list[dict]:
    async with _connect() as conn:
        conn.row_factory = _dict_factory
        cur = await conn.execute(
            """
            SELECT bc.user_id, bc.username, bc.last_incoming_at, bc.connection_id
            FROM business_contacts bc
            JOIN business_connections c ON c.connection_id = bc.connection_id
            WHERE c.user_id = ? AND c.is_enabled = 1 AND c.can_reply = 1
            ORDER BY bc.last_incoming_at DESC LIMIT ?
            """,
            (owner_id, limit),
        )
        return await cur.fetchall()


async def create_offer(*, business_connection_id: str, owner_id: int, owner_username: str | None,
                       recipient_id: int, chat_id: int, nft_url: str, gift_name: str,
                       gift_number: str, amount: str, currency: str) -> int:
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


async def create_inline_offer(*, owner_id: int, owner_username: str | None,
                             nft_url: str, gift_name: str, gift_number: str,
                             amount: str, currency: str) -> int:
    """Create an offer for an inline result. Each result keeps its own terms."""
    async with _connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO offers (business_connection_id, owner_id, owner_username,
                                recipient_id, chat_id, nft_url, gift_name, gift_number,
                                amount, currency, status, created_at)
            VALUES ('inline', ?, ?, 0, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (owner_id, owner_username, owner_id, nft_url, gift_name, gift_number,
             amount, currency, _now()),
        )
        await conn.commit()
        return cur.lastrowid


async def assign_inline_recipient(offer_id: int, recipient_id: int) -> bool:
    async with _connect() as conn:
        cur = await conn.execute(
            """
            UPDATE offers SET recipient_id = ?
            WHERE id = ? AND business_connection_id = 'inline'
              AND recipient_id = 0 AND status = 'pending'
            """,
            (recipient_id, offer_id),
        )
        await conn.commit()
        return cur.rowcount == 1


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
    async with _connect() as conn:
        cur = await conn.execute(
            "UPDATE offers SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
            (new_status, _now(), offer_id),
        )
        await conn.commit()
        return cur.rowcount == 1


async def get_connection(connection_id: str) -> dict | None:
    """Return the stored Telegram Business connection for an incoming update."""
    async with _connect() as conn:
        conn.row_factory = _dict_factory
        cur = await conn.execute(
            "SELECT * FROM business_connections WHERE connection_id = ? LIMIT 1",
            (connection_id,),
        )
        return await cur.fetchone()
