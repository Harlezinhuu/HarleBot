"""Conquistas: contadores dos jogos e insígnias desbloqueadas."""
import asyncio
import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from conteudo.conquistas import CONQUISTAS
from utils import embeds, moeda

log = logging.getLogger("harle.conquistas")


async def registrar(bot, guild_id: int, user_id: int, stat: str, n: int = 1, *, maximo: Optional[int] = None,
                    canal: Optional[discord.abc.Messageable] = None) -> List[dict]:
    """Atalho para os outros módulos: `await registrar(self.bot, g, u, "truco_vitorias", canal=...)`.

    Nunca derruba quem chamou: se der algum erro, só registra no console.
    """
    try:
        cog = bot.get_cog("Conquistas")
        if cog is None or user_id <= 0:
            return []
        return await cog.registrar(guild_id, user_id, stat, n, maximo=maximo, canal=canal)
    except Exception:
        log.exception("Erro ao registrar a conquista %s", stat)
        return []


def registrar_depois(bot, guild_id: int, user_id: int, stat: str, n: int = 1, *, maximo: Optional[int] = None,
                     canal: Optional[discord.abc.Messageable] = None):
    """Mesma coisa que `registrar`, mas em segundo plano (não atrasa a resposta do jogo)."""
    asyncio.create_task(registrar(bot, guild_id, user_id, stat, n, maximo=maximo, canal=canal))


class Conquistas(commands.Cog, name="Conquistas"):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def registrar(self, guild_id: int, user_id: int, stat: str, n: int = 1, *, maximo: Optional[int] = None,
                        canal: Optional[discord.abc.Messageable] = None) -> List[dict]:
        if maximo is not None:
            valor = await self.db.stat_maximo(guild_id, user_id, stat, maximo)
        else:
            valor = await self.db.stat_somar(guild_id, user_id, stat, n)

        novas = []
        for c in CONQUISTAS:
            if c["stat"] == stat and valor >= c["meta"]:
                if await self.db.conquista_desbloquear(guild_id, user_id, c["id"]):
                    novas.append(c)
                    if c["premio"]:
                        await self.db.add_coins(guild_id, user_id, c["premio"])
        if novas and canal is not None:
            linhas = [f"{c['emoji']} **{c['nome']}** — {c['descricao']}"
                      + (f" (+{moeda.fmt(c['premio'])})" if c["premio"] else "") for c in novas]
            e = discord.Embed(title="🏅 Conquista desbloqueada!", color=embeds.AMBAR,
                              description=f"<@{user_id}>\n" + "\n".join(linhas))
            try:
                await canal.send(embed=e, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
        return novas

    @app_commands.command(name="conquistas", description="Mostra as conquistas que você (ou alguém) já desbloqueou.")
    @app_commands.describe(membro="De quem ver as conquistas")
    @app_commands.guild_only()
    async def conquistas(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        membro = membro or interaction.user
        g, u = interaction.guild.id, membro.id
        feitas = set(await self.db.conquistas(g, u))
        stats = await self.db.stats(g, u)
        e = discord.Embed(title=f"🏅 Conquistas de {membro.display_name}", color=embeds.AMBAR,
                          description=f"**{len(feitas)}** de **{len(CONQUISTAS)}** desbloqueadas")
        e.set_thumbnail(url=membro.display_avatar.url)
        feitas_txt, faltando_txt = [], []
        for c in CONQUISTAS:
            if c["id"] in feitas:
                feitas_txt.append(f"{c['emoji']} **{c['nome']}**")
            else:
                progresso = min(stats.get(c["stat"], 0), c["meta"])
                meta = f"{c['meta']:,}".replace(",", ".")
                feito = f"{progresso:,}".replace(",", ".")
                faltando_txt.append(f"🔒 **{c['nome']}** · {c['descricao']} ({feito}/{meta})")
        if feitas_txt:
            e.add_field(name="Desbloqueadas", value=embeds.cortar("\n".join(feitas_txt), 1024), inline=False)
        if faltando_txt:
            e.add_field(name="Para conseguir", value=embeds.cortar("\n".join(faltando_txt), 1024), inline=False)
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Conquistas(bot))
