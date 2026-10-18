"""Banco de dados do bot (SQLite). Um arquivo só, sem precisar instalar servidor."""
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

-- ---------- Etapa 2: economia e níveis ----------

CREATE TABLE IF NOT EXISTS economy (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    coins       INTEGER NOT NULL DEFAULT 0,
    last_daily  INTEGER,
    streak      INTEGER NOT NULL DEFAULT 0,
    last_work   INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS shop (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id  INTEGER NOT NULL,
    role_id   INTEGER NOT NULL,
    price     INTEGER NOT NULL,
    UNIQUE (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS levels (
    guild_id  INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    xp        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS level_rewards (
    guild_id  INTEGER NOT NULL,
    level     INTEGER NOT NULL,
    role_id   INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);

CREATE TABLE IF NOT EXISTS inventory (
    guild_id  INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    item_id   TEXT    NOT NULL,
    quantity  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, item_id)
);

CREATE TABLE IF NOT EXISTS profile (
    guild_id  INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    about     TEXT,
    theme     TEXT,
    title     TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS boosts (
    guild_id  INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    boost     TEXT    NOT NULL,
    until     INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, boost)
);

CREATE TABLE IF NOT EXISTS music_247 (
    guild_id    INTEGER PRIMARY KEY,
    channel_id  INTEGER NOT NULL
);

-- ---------- proteção e cargos ----------

CREATE TABLE IF NOT EXISTS automod (
    guild_id        INTEGER PRIMARY KEY,
    ativo           INTEGER NOT NULL DEFAULT 0,
    anti_spam       INTEGER NOT NULL DEFAULT 1,
    anti_links      INTEGER NOT NULL DEFAULT 0,
    anti_convites   INTEGER NOT NULL DEFAULT 1,
    anti_caps       INTEGER NOT NULL DEFAULT 0,
    anti_mencoes    INTEGER NOT NULL DEFAULT 1,
    limite_mencoes  INTEGER NOT NULL DEFAULT 5,
    punicao         TEXT    NOT NULL DEFAULT 'silenciar'
);

CREATE TABLE IF NOT EXISTS automod_palavras (
    guild_id  INTEGER NOT NULL,
    palavra   TEXT    NOT NULL,
    PRIMARY KEY (guild_id, palavra)
);

CREATE TABLE IF NOT EXISTS automod_ignorados (
    guild_id  INTEGER NOT NULL,
    alvo_id   INTEGER NOT NULL,     -- canal ou cargo
    PRIMARY KEY (guild_id, alvo_id)
);

CREATE TABLE IF NOT EXISTS antiraid (
    guild_id      INTEGER PRIMARY KEY,
    ativo         INTEGER NOT NULL DEFAULT 0,
    limite        INTEGER NOT NULL DEFAULT 8,
    janela        INTEGER NOT NULL DEFAULT 15,
    acao          TEXT    NOT NULL DEFAULT 'verificacao',
    idade_minima  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS role_panels (
    message_id   INTEGER PRIMARY KEY,
    guild_id     INTEGER NOT NULL,
    channel_id   INTEGER NOT NULL,
    titulo       TEXT    NOT NULL,
    descricao    TEXT,
    modo         TEXT    NOT NULL,          -- 'botoes' ou 'reacoes'
    unico        INTEGER NOT NULL DEFAULT 0 -- 1 = só um cargo do painel por pessoa
);

CREATE TABLE IF NOT EXISTS role_panel_items (
    message_id  INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    emoji       TEXT,
    rotulo      TEXT,
    PRIMARY KEY (message_id, role_id)
);

CREATE TABLE IF NOT EXISTS level_settings (
    guild_id    INTEGER PRIMARY KEY,
    announce    INTEGER NOT NULL DEFAULT 1,
    channel_id  INTEGER
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
        if self.path != ":memory:":
            # WAL + synchronous NORMAL: gravações bem mais rápidas, sem perder segurança na prática
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA synchronous=NORMAL")
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

    # ---------- economia ----------

    async def _garantir_carteira(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id)
        )

    async def get_wallet(self, guild_id: int, user_id: int) -> aiosqlite.Row:
        await self._garantir_carteira(guild_id, user_id)
        await self.conn.commit()
        async with self.conn.execute(
            "SELECT * FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        ) as cur:
            return await cur.fetchone()

    async def add_coins(self, guild_id: int, user_id: int, delta: int) -> int:
        """Soma (ou tira) moedas sem nunca deixar o saldo negativo. Devolve o saldo novo."""
        await self._garantir_carteira(guild_id, user_id)
        await self.conn.execute(
            "UPDATE economy SET coins = MAX(coins + ?, 0) WHERE guild_id = ? AND user_id = ?",
            (delta, guild_id, user_id),
        )
        await self.conn.commit()
        return (await self.get_wallet(guild_id, user_id))["coins"]

    async def spend_coins(self, guild_id: int, user_id: int, amount: int) -> bool:
        """Tira `amount` moedas só se a pessoa tiver o suficiente. Devolve se deu certo."""
        await self._garantir_carteira(guild_id, user_id)
        cur = await self.conn.execute(
            "UPDATE economy SET coins = coins - ? WHERE guild_id = ? AND user_id = ? AND coins >= ?",
            (amount, guild_id, user_id, amount),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def transfer(self, guild_id: int, de: int, para: int, amount: int) -> bool:
        if not await self.spend_coins(guild_id, de, amount):
            return False
        await self.add_coins(guild_id, para, amount)
        return True

    async def set_daily(self, guild_id: int, user_id: int, quando: int, streak: int):
        await self._garantir_carteira(guild_id, user_id)
        await self.conn.execute(
            "UPDATE economy SET last_daily = ?, streak = ? WHERE guild_id = ? AND user_id = ?",
            (quando, streak, guild_id, user_id),
        )
        await self.conn.commit()

    async def set_work(self, guild_id: int, user_id: int, quando: int):
        await self._garantir_carteira(guild_id, user_id)
        await self.conn.execute(
            "UPDATE economy SET last_work = ? WHERE guild_id = ? AND user_id = ?", (quando, guild_id, user_id)
        )
        await self.conn.commit()

    async def add_coins_varios(self, guild_id: int, user_ids: List[int], delta: int) -> int:
        """Soma `delta` para cada pessoa da lista (cria a carteira se não existir). Devolve quantas."""
        await self.conn.executemany(
            "INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", [(guild_id, u) for u in user_ids])
        await self.conn.executemany(
            "UPDATE economy SET coins = MAX(coins + ?, 0) WHERE guild_id = ? AND user_id = ?",
            [(delta, guild_id, u) for u in user_ids])
        await self.conn.commit()
        return len(user_ids)

    async def tirar_coins_de_todos(self, guild_id: int, quantidade: int) -> int:
        """Tira `quantidade` de todas as carteiras do servidor (sem ficar negativo). Devolve quantas mudaram."""
        cur = await self.conn.execute(
            "UPDATE economy SET coins = MAX(coins - ?, 0) WHERE guild_id = ? AND coins > 0", (quantidade, guild_id))
        await self.conn.commit()
        return cur.rowcount

    async def zerar_coins(self, guild_id: int) -> int:
        cur = await self.conn.execute("UPDATE economy SET coins = 0 WHERE guild_id = ? AND coins > 0", (guild_id,))
        await self.conn.commit()
        return cur.rowcount

    async def top_coins(self, guild_id: int, limite: int = 10) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT user_id, coins FROM economy WHERE guild_id = ? AND coins > 0 ORDER BY coins DESC LIMIT ?",
            (guild_id, limite),
        ) as cur:
            return list(await cur.fetchall())

    # ---------- loja ----------

    async def shop_add(self, guild_id: int, role_id: int, price: int):
        await self.conn.execute(
            "INSERT INTO shop (guild_id, role_id, price) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, role_id) DO UPDATE SET price = excluded.price",
            (guild_id, role_id, price),
        )
        await self.conn.commit()

    async def shop_remove(self, guild_id: int, role_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM shop WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        await self.conn.commit()
        return cur.rowcount > 0

    async def shop_list(self, guild_id: int) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM shop WHERE guild_id = ? ORDER BY price", (guild_id,)
        ) as cur:
            return list(await cur.fetchall())

    async def shop_get(self, guild_id: int, role_id: int) -> Optional[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM shop WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        ) as cur:
            return await cur.fetchone()

    # ---------- níveis ----------

    async def add_xp(self, guild_id: int, user_id: int, quantidade: int) -> Tuple[int, int]:
        """Soma XP e devolve (xp_antes, xp_depois)."""
        antes = await self.get_xp(guild_id, user_id)
        await self.conn.execute(
            "INSERT INTO levels (guild_id, user_id, xp) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = xp + excluded.xp",
            (guild_id, user_id, quantidade),
        )
        await self.conn.commit()
        return antes, antes + quantidade

    async def get_xp(self, guild_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
        return row["xp"] if row else 0

    async def xp_rank(self, guild_id: int, user_id: int) -> int:
        """Posição da pessoa no ranking de XP do servidor (1 = primeiro)."""
        xp = await self.get_xp(guild_id, user_id)
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM levels WHERE guild_id = ? AND xp > ?", (guild_id, xp)
        ) as cur:
            return (await cur.fetchone())["n"] + 1

    async def top_xp(self, guild_id: int, limite: int = 10) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT user_id, xp FROM levels WHERE guild_id = ? AND xp > 0 ORDER BY xp DESC LIMIT ?",
            (guild_id, limite),
        ) as cur:
            return list(await cur.fetchall())

    async def reward_set(self, guild_id: int, level: int, role_id: int):
        await self.conn.execute(
            "INSERT INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id",
            (guild_id, level, role_id),
        )
        await self.conn.commit()

    async def reward_remove(self, guild_id: int, level: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM level_rewards WHERE guild_id = ? AND level = ?", (guild_id, level)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def rewards_list(self, guild_id: int) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM level_rewards WHERE guild_id = ? ORDER BY level", (guild_id,)
        ) as cur:
            return list(await cur.fetchall())

    async def get_level_settings(self, guild_id: int) -> Tuple[bool, Optional[int]]:
        """Devolve (anunciar_subida_de_nivel, canal_dos_anuncios)."""
        async with self.conn.execute(
            "SELECT announce, channel_id FROM level_settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return True, None
        return bool(row["announce"]), row["channel_id"]

    # ---------- inventário, perfil e boosts ----------

    async def inv_add(self, guild_id: int, user_id: int, item_id: str, quantidade: int = 1):
        await self.conn.execute(
            "INSERT INTO inventory (guild_id, user_id, item_id, quantity) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity",
            (guild_id, user_id, item_id, quantidade),
        )
        await self.conn.commit()

    async def inv_count(self, guild_id: int, user_id: int, item_id: str) -> int:
        async with self.conn.execute(
            "SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?",
            (guild_id, user_id, item_id),
        ) as cur:
            row = await cur.fetchone()
        return row["quantity"] if row else 0

    async def inv_list(self, guild_id: int, user_id: int) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT item_id, quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND quantity > 0",
            (guild_id, user_id),
        ) as cur:
            return list(await cur.fetchall())

    async def inv_use(self, guild_id: int, user_id: int, item_id: str) -> bool:
        """Gasta 1 unidade do item. Devolve se a pessoa tinha."""
        cur = await self.conn.execute(
            "UPDATE inventory SET quantity = quantity - 1 "
            "WHERE guild_id = ? AND user_id = ? AND item_id = ? AND quantity > 0",
            (guild_id, user_id, item_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def profile_get(self, guild_id: int, user_id: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Devolve (sobre_mim, tema, titulo)."""
        async with self.conn.execute(
            "SELECT about, theme, title FROM profile WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
        return (row["about"], row["theme"], row["title"]) if row else (None, None, None)

    async def profile_set(self, guild_id: int, user_id: int, campo: str, valor: Optional[str]):
        if campo not in ("about", "theme", "title"):
            raise ValueError(campo)
        await self.conn.execute(
            "INSERT OR IGNORE INTO profile (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id)
        )
        await self.conn.execute(
            f"UPDATE profile SET {campo} = ? WHERE guild_id = ? AND user_id = ?", (valor, guild_id, user_id)
        )
        await self.conn.commit()

    async def boost_activate(self, guild_id: int, user_id: int, boost: str, segundos: int, agora: int) -> int:
        """Liga (ou estende) um boost. Devolve até quando ele vale."""
        atual = await self.boost_until(guild_id, user_id, boost)
        ate = max(atual, agora) + segundos
        await self.conn.execute(
            "INSERT INTO boosts (guild_id, user_id, boost, until) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, boost) DO UPDATE SET until = excluded.until",
            (guild_id, user_id, boost, ate),
        )
        await self.conn.commit()
        return ate

    async def boost_until(self, guild_id: int, user_id: int, boost: str) -> int:
        async with self.conn.execute(
            "SELECT until FROM boosts WHERE guild_id = ? AND user_id = ? AND boost = ?", (guild_id, user_id, boost)
        ) as cur:
            row = await cur.fetchone()
        return row["until"] if row else 0

    # ---------- automod ----------

    CAMPOS_AUTOMOD = ("ativo", "anti_spam", "anti_links", "anti_convites", "anti_caps", "anti_mencoes",
                      "limite_mencoes", "punicao")

    async def get_automod(self, guild_id: int) -> Dict:
        async with self.conn.execute("SELECT * FROM automod WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return {"ativo": 0, "anti_spam": 1, "anti_links": 0, "anti_convites": 1, "anti_caps": 0,
                    "anti_mencoes": 1, "limite_mencoes": 5, "punicao": "silenciar"}
        return {k: row[k] for k in self.CAMPOS_AUTOMOD}

    async def set_automod(self, guild_id: int, **campos):
        campos = {k: v for k, v in campos.items() if k in self.CAMPOS_AUTOMOD and v is not None}
        await self.conn.execute("INSERT OR IGNORE INTO automod (guild_id) VALUES (?)", (guild_id,))
        if campos:
            sets = ", ".join(f"{k} = ?" for k in campos)
            await self.conn.execute(f"UPDATE automod SET {sets} WHERE guild_id = ?", (*campos.values(), guild_id))
        await self.conn.commit()

    async def palavras_proibidas(self, guild_id: int) -> List[str]:
        async with self.conn.execute(
            "SELECT palavra FROM automod_palavras WHERE guild_id = ? ORDER BY palavra", (guild_id,)
        ) as cur:
            return [r["palavra"] for r in await cur.fetchall()]

    async def palavra_adicionar(self, guild_id: int, palavra: str):
        await self.conn.execute("INSERT OR IGNORE INTO automod_palavras VALUES (?, ?)", (guild_id, palavra))
        await self.conn.commit()

    async def palavra_remover(self, guild_id: int, palavra: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM automod_palavras WHERE guild_id = ? AND palavra = ?", (guild_id, palavra))
        await self.conn.commit()
        return cur.rowcount > 0

    async def ignorados(self, guild_id: int) -> List[int]:
        async with self.conn.execute("SELECT alvo_id FROM automod_ignorados WHERE guild_id = ?", (guild_id,)) as cur:
            return [r["alvo_id"] for r in await cur.fetchall()]

    async def alternar_ignorado(self, guild_id: int, alvo_id: int) -> bool:
        """Liga/desliga a exceção. Devolve True se agora está sendo ignorado."""
        cur = await self.conn.execute(
            "DELETE FROM automod_ignorados WHERE guild_id = ? AND alvo_id = ?", (guild_id, alvo_id))
        if cur.rowcount == 0:
            await self.conn.execute("INSERT INTO automod_ignorados VALUES (?, ?)", (guild_id, alvo_id))
        await self.conn.commit()
        return cur.rowcount == 0

    # ---------- anti-raid ----------

    async def get_antiraid(self, guild_id: int) -> Dict:
        async with self.conn.execute("SELECT * FROM antiraid WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return {"ativo": 0, "limite": 8, "janela": 15, "acao": "verificacao", "idade_minima": 0}
        return {k: row[k] for k in ("ativo", "limite", "janela", "acao", "idade_minima")}

    async def set_antiraid(self, guild_id: int, **campos):
        campos = {k: v for k, v in campos.items()
                  if k in ("ativo", "limite", "janela", "acao", "idade_minima") and v is not None}
        await self.conn.execute("INSERT OR IGNORE INTO antiraid (guild_id) VALUES (?)", (guild_id,))
        if campos:
            sets = ", ".join(f"{k} = ?" for k in campos)
            await self.conn.execute(f"UPDATE antiraid SET {sets} WHERE guild_id = ?", (*campos.values(), guild_id))
        await self.conn.commit()

    # ---------- painéis de cargos ----------

    async def painel_criar(self, message_id: int, guild_id: int, channel_id: int, titulo: str,
                           descricao: Optional[str], modo: str, unico: bool):
        await self.conn.execute(
            "INSERT INTO role_panels VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, guild_id, channel_id, titulo, descricao, modo, int(unico)))
        await self.conn.commit()

    async def painel(self, message_id: int) -> Optional[aiosqlite.Row]:
        async with self.conn.execute("SELECT * FROM role_panels WHERE message_id = ?", (message_id,)) as cur:
            return await cur.fetchone()

    async def painel_itens(self, message_id: int) -> List[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM role_panel_items WHERE message_id = ? ORDER BY rowid", (message_id,)
        ) as cur:
            return list(await cur.fetchall())

    async def painel_item_salvar(self, message_id: int, role_id: int, emoji: Optional[str], rotulo: Optional[str]):
        await self.conn.execute(
            "INSERT INTO role_panel_items VALUES (?, ?, ?, ?) "
            "ON CONFLICT(message_id, role_id) DO UPDATE SET emoji = excluded.emoji, rotulo = excluded.rotulo",
            (message_id, role_id, emoji, rotulo))
        await self.conn.commit()

    async def painel_item_remover(self, message_id: int, role_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM role_panel_items WHERE message_id = ? AND role_id = ?", (message_id, role_id))
        await self.conn.commit()
        return cur.rowcount > 0

    async def painel_apagar(self, message_id: int):
        await self.conn.execute("DELETE FROM role_panel_items WHERE message_id = ?", (message_id,))
        await self.conn.execute("DELETE FROM role_panels WHERE message_id = ?", (message_id,))
        await self.conn.commit()

    # ---------- música 24/7 ----------

    async def set_247(self, guild_id: int, channel_id: Optional[int]):
        if channel_id is None:
            await self.conn.execute("DELETE FROM music_247 WHERE guild_id = ?", (guild_id,))
        else:
            await self.conn.execute(
                "INSERT INTO music_247 (guild_id, channel_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
                (guild_id, channel_id),
            )
        await self.conn.commit()

    async def get_247(self, guild_id: int) -> Optional[int]:
        async with self.conn.execute("SELECT channel_id FROM music_247 WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
        return row["channel_id"] if row else None

    async def list_247(self) -> List[aiosqlite.Row]:
        async with self.conn.execute("SELECT guild_id, channel_id FROM music_247") as cur:
            return list(await cur.fetchall())

    async def set_level_settings(self, guild_id: int, announce: bool, channel_id: Optional[int]):
        await self.conn.execute(
            "INSERT INTO level_settings (guild_id, announce, channel_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET announce = excluded.announce, channel_id = excluded.channel_id",
            (guild_id, int(announce), channel_id),
        )
        await self.conn.commit()
