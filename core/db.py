"""Banco de dados do bot (SQLite). Um arquivo só, sem precisar instalar servidor."""
import time
from pathlib import Path
from typing import List, Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id        INTEGER PRIMARY KEY,
    log_channel_id  INTEGER
);

CREATE TABLE IF NOT EXISTS warnings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    moderator_id  INTEGER NOT NULL,
    reason        TEXT    NOT NULL,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings (guild_id, user_id);

CREATE TABLE IF NOT EXISTS cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    case_number   INTEGER NOT NULL,
    action        TEXT    NOT NULL,
    user_id       INTEGER NOT NULL,
    moderator_id  INTEGER NOT NULL,
    reason        TEXT,
    created_at    INTEGER NOT NULL,
    UNIQUE (guild_id, case_number)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    # ---------- configurações do servidor ----------

    async def get_log_channel(self, guild_id: int) -> Optional[int]:
        async with self.conn.execute(
            "SELECT log_channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        return row["log_channel_id"] if row else None

    async def set_log_channel(self, guild_id: int, channel_id: Optional[int]):
        await self.conn.execute(
            "INSERT INTO guild_settings (guild_id, log_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id",
            (guild_id, channel_id),
        )
        await self.conn.commit()

    # ---------- avisos ----------

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        cur = await self.conn.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def list_warnings(self, guild_id: int, user_id: int) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id",
            (guild_id, user_id),
        ) as cur:
            return list(await cur.fetchall())

    async def remove_warning(self, guild_id: int, warning_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND id = ?", (guild_id, warning_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        cur = await self.conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await self.conn.commit()
        return cur.rowcount

    # ---------- casos (histórico de punições) ----------

    async def add_case(self, guild_id: int, action: str, user_id: int, moderator_id: int,
                       reason: Optional[str]) -> int:
        """Registra uma ação de moderação e devolve o número do caso no servidor (#1, #2...)."""
        async with self.conn.execute(
            "SELECT COALESCE(MAX(case_number), 0) + 1 AS n FROM cases WHERE guild_id = ?", (guild_id,)
        ) as cur:
            numero = (await cur.fetchone())["n"]
        await self.conn.execute(
            "INSERT INTO cases (guild_id, case_number, action, user_id, moderator_id, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, numero, action, user_id, moderator_id, reason, int(time.time())),
        )
        await self.conn.commit()
        return numero
