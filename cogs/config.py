"""Configurações do bot em cada servidor."""
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds


class Config(commands.Cog, name="Configuração"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="config-logs", description="Escolhe o canal onde o bot registra tudo (vazio = desligar).")
    @app_commands.describe(canal="Canal dos registros. Deixe vazio para desligar.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_logs(self, interaction: discord.Interaction, canal: Optional[discord.TextChannel] = None):
        if canal is None:
            await self.bot.db.set_log_channel(interaction.guild.id, None)
            return await interaction.response.send_message(
                embed=embeds.sucesso("Registros desligados."), ephemeral=True)

        perms = canal.permissions_for(interaction.guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            return await interaction.response.send_message(
                embed=embeds.erro(f"Não consigo escrever em {canal.mention}. Me dê as permissões "
                                  "**Ver canal**, **Enviar mensagens** e **Inserir links** nele."),
                ephemeral=True)

        await self.bot.db.set_log_channel(interaction.guild.id, canal.id)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"Pronto! Os registros vão para {canal.mention}."), ephemeral=True)
        await canal.send(embed=discord.Embed(
            title="📋 Registros ativados",
            description="Punições, mensagens apagadas ou editadas e entradas e saídas de membros vão aparecer aqui.",
            color=embeds.AZUL,
        ))


async def setup(bot):
    await bot.add_cog(Config(bot))
