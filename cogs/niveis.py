"""Níveis: XP por conversar no chat, ranking e cargos de recompensa."""
import random
import time
from typing import Dict, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds, moeda
from utils.niveis import barra, nivel_de
from cogs.conquistas import registrar_depois

XP_MIN, XP_MAX = 15, 25
INTERVALO_XP = 60          # segundos entre mensagens que contam XP (evita farm de spam)
MOEDAS_POR_NIVEL = 50      # ao subir para o nível N, ganha N * 50 moedas


class Niveis(commands.Cog, name="Níveis"):
    def __init__(self, bot):
        self.bot = bot
        self._ultima_xp: Dict[Tuple[int, int], float] = {}

    @property
    def db(self):
        return self.bot.db

    # ---------- ganhar XP ----------

    @commands.Cog.listener()
    async def on_message(self, mensagem: discord.Message):
        if mensagem.guild is None or mensagem.author.bot or not isinstance(mensagem.author, discord.Member):
            return
        chave = (mensagem.guild.id, mensagem.author.id)
        agora = time.monotonic()
        if agora - self._ultima_xp.get(chave, 0) < INTERVALO_XP:
            return
        self._ultima_xp[chave] = agora
        if len(self._ultima_xp) > 20_000:  # limpa a memória de vez em quando
            self._ultima_xp = {k: v for k, v in self._ultima_xp.items() if agora - v < INTERVALO_XP}

        xp = random.randint(XP_MIN, XP_MAX)
        if await self.db.boost_until(mensagem.guild.id, mensagem.author.id, "boost_xp") > time.time():
            xp *= 2
        antes, depois = await self.db.add_xp(mensagem.guild.id, mensagem.author.id, xp)
        nivel_antes, nivel_depois = nivel_de(antes)[0], nivel_de(depois)[0]
        if nivel_depois > nivel_antes:
            await self._subiu_de_nivel(mensagem, nivel_depois)
            registrar_depois(self.bot, mensagem.guild.id, mensagem.author.id, "max_nivel", maximo=nivel_depois,
                             canal=mensagem.channel)

    async def _subiu_de_nivel(self, mensagem: discord.Message, nivel: int):
        guild, membro = mensagem.guild, mensagem.author
        premio = nivel * MOEDAS_POR_NIVEL
        await self.db.add_coins(guild.id, membro.id, premio)
        novos_cargos = await self._entregar_recompensas(membro, nivel)

        anunciar, canal_id = await self.db.get_level_settings(guild.id)
        if not anunciar:
            return
        canal = guild.get_channel(canal_id) if canal_id else mensagem.channel
        if canal is None:
            canal = mensagem.channel

        texto = f"🎉 {membro.mention} subiu para o **nível {nivel}** e ganhou {moeda.fmt(premio)}!"
        if novos_cargos:
            texto += "\nNovo cargo: " + ", ".join(c.mention for c in novos_cargos)
        try:
            await canal.send(texto, allowed_mentions=discord.AllowedMentions(users=[membro], roles=False))
        except discord.HTTPException:
            pass

    async def _entregar_recompensas(self, membro: discord.Member, nivel: int):
        """Dá todos os cargos de recompensa até o nível atual que a pessoa ainda não tem."""
        entregues = []
        topo_do_bot = membro.guild.me.top_role
        for recompensa in await self.db.rewards_list(membro.guild.id):
            if recompensa["level"] > nivel:
                break
            cargo = membro.guild.get_role(recompensa["role_id"])
            if cargo and cargo not in membro.roles and cargo < topo_do_bot:
                try:
                    await membro.add_roles(cargo, reason=f"Recompensa do nível {recompensa['level']}")
                    entregues.append(cargo)
                except discord.HTTPException:
                    pass
        return entregues

    # ---------- comandos ----------

    @app_commands.command(name="nivel", description="Mostra seu nível e XP (ou de outra pessoa).")
    @app_commands.describe(membro="De quem ver o nível")
    @app_commands.guild_only()
    async def nivel(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        membro = membro or interaction.user
        if membro.bot:
            return await interaction.response.send_message(embed=embeds.erro("Bots não ganham XP."), ephemeral=True)
        xp = await self.db.get_xp(interaction.guild.id, membro.id)
        nivel, atual, precisa = nivel_de(xp)
        posicao = await self.db.xp_rank(interaction.guild.id, membro.id)

        e = discord.Embed(title=f"Nível de {membro.display_name}", color=embeds.AZUL)
        e.add_field(name="Nível", value=f"**{nivel}**")
        e.add_field(name="Ranking", value=f"#{posicao}")
        e.add_field(name="XP total", value=f"{xp:,}".replace(",", "."))
        e.add_field(name=f"Progresso para o nível {nivel + 1}",
                    value=f"{barra(atual, precisa)} {atual}/{precisa}", inline=False)
        e.set_thumbnail(url=membro.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="ranking-xp", description="Quem mais conversa no servidor.")
    @app_commands.guild_only()
    async def ranking_xp(self, interaction: discord.Interaction):
        top = await self.db.top_xp(interaction.guild.id)
        if not top:
            return await interaction.response.send_message(
                embed=embeds.erro("Ninguém ganhou XP ainda. É só conversar no chat!"), ephemeral=True)
        medalhas = ["🥇", "🥈", "🥉"]
        linhas = []
        for i, r in enumerate(top):
            pos = medalhas[i] if i < 3 else f"`{i + 1}.`"
            linhas.append(f"{pos} <@{r['user_id']}> · nível **{nivel_de(r['xp'])[0]}**")
        e = discord.Embed(title="📈 Ranking de níveis", color=embeds.AZUL, description="\n".join(linhas))
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="recompensas", description="Mostra os cargos que se ganha ao subir de nível.")
    @app_commands.guild_only()
    async def recompensas(self, interaction: discord.Interaction):
        lista = await self.db.rewards_list(interaction.guild.id)
        if not lista:
            return await interaction.response.send_message(
                embed=embeds.erro("Ainda não há cargos de recompensa. A administração usa `/recompensa-adicionar`."),
                ephemeral=True)
        linhas = [f"Nível **{r['level']}** → <@&{r['role_id']}>" for r in lista]
        await interaction.response.send_message(
            embed=discord.Embed(title="🏅 Recompensas por nível", color=embeds.AZUL, description="\n".join(linhas)))

    @app_commands.command(name="recompensa-adicionar", description="Dá um cargo automaticamente quem chegar a um nível.")
    @app_commands.describe(nivel="Nível necessário", cargo="Cargo que a pessoa ganha")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def recompensa_adicionar(self, interaction: discord.Interaction,
                                   nivel: app_commands.Range[int, 1, 500], cargo: discord.Role):
        if cargo.is_default() or cargo.managed or cargo >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                embed=embeds.erro("Não consigo entregar esse cargo. Ele precisa estar abaixo do meu."), ephemeral=True)
        await self.db.reward_set(interaction.guild.id, nivel, cargo.id)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"Quem chegar ao nível {nivel} vai ganhar {cargo.mention}."), ephemeral=True)

    @app_commands.command(name="recompensa-remover", description="Tira a recompensa de um nível.")
    @app_commands.describe(nivel="Nível da recompensa")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def recompensa_remover(self, interaction: discord.Interaction, nivel: app_commands.Range[int, 1, 500]):
        if await self.db.reward_remove(interaction.guild.id, nivel):
            await interaction.response.send_message(embed=embeds.sucesso("Recompensa removida."), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=embeds.erro("Não tinha recompensa nesse nível."), ephemeral=True)

    @app_commands.command(name="config-niveis", description="Liga/desliga o aviso de subir de nível e escolhe o canal.")
    @app_commands.describe(avisos="Avisar quando alguém sobe de nível?",
                           canal="Canal dos avisos (vazio = no mesmo canal da mensagem)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_niveis(self, interaction: discord.Interaction, avisos: bool,
                            canal: Optional[discord.TextChannel] = None):
        await self.db.set_level_settings(interaction.guild.id, avisos, canal.id if canal else None)
        if not avisos:
            texto = "Avisos de nível desligados. O XP continua contando normalmente."
        elif canal:
            texto = f"Os avisos de nível vão para {canal.mention}."
        else:
            texto = "Os avisos de nível vão aparecer no mesmo canal da mensagem."
        await interaction.response.send_message(embed=embeds.sucesso(texto), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Niveis(bot))
