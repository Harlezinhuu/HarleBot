"""Comandos gerais: ajuda e ping."""
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

ORDEM = ["Geral", "Moderação", "Configuração"]
SITE = "https://harlezinhuu.github.io"


class Geral(commands.Cog, name="Geral"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ajuda", description="Mostra tudo que o bot sabe fazer.")
    async def ajuda(self, interaction: discord.Interaction):
        grupos = {}
        for cmd in self.bot.tree.get_commands():
            if isinstance(cmd, app_commands.Command):
                nome = cmd.binding.qualified_name if cmd.binding else "Geral"
                grupos.setdefault(nome, []).append(cmd)

        e = discord.Embed(title="Comandos do Harle Bot", color=embeds.AZUL,
                          description="Digite `/` no chat para ver e usar qualquer um deles.")
        for nome in sorted(grupos, key=lambda n: ORDEM.index(n) if n in ORDEM else len(ORDEM)):
            linhas = [f"`/{c.name}` {c.description}" for c in sorted(grupos[nome], key=lambda c: c.name)]
            e.add_field(name=nome, value=embeds.cortar("\n".join(linhas), 1024), inline=False)
        e.set_footer(text=f"Feito por Harle · {SITE.removeprefix('https://')}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="ping", description="Mostra se o bot está respondendo rápido.")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(embed=embeds.sucesso(f"Pong! {ms} ms"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Geral(bot))
