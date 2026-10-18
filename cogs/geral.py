"""Comandos gerais: ajuda e ping."""
import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

ORDEM = ["Geral", "Música", "Jogos", "Truco", "Xadrez", "Cassino", "Batalha", "Economia", "Loja e Perfil", "Níveis", "Moderação", "Proteção", "Cargos", "Configuração"]
SITE = "https://harlezinhuu.github.io"


class Geral(commands.Cog, name="Geral"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ajuda", description="Mostra tudo que o bot sabe fazer.")
    async def ajuda(self, interaction: discord.Interaction):
        grupos = {}
        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Command):   # inclui subcomandos, como /automod configurar
                nome = cmd.binding.qualified_name if cmd.binding else "Geral"
                grupos.setdefault(nome, []).append(cmd)

        e = discord.Embed(title="Comandos do Harle Bot", color=embeds.AZUL,
                          description="Digite `/` no chat para ver e usar qualquer um deles.")
        for nome in sorted(grupos, key=lambda n: ORDEM.index(n) if n in ORDEM else len(ORDEM)):
            def restrito(c):
                return bool(c.default_permissions or (c.parent and c.parent.default_permissions))
            linhas = [f"{'🔒 ' if restrito(c) else ''}`/{c.qualified_name}` {c.description}"
                      for c in sorted(grupos[nome], key=lambda c: c.qualified_name)]
            # um campo aceita até 1024 caracteres; se passar, divide em mais campos
            bloco, primeiro = "", True
            for linha in linhas:
                if len(bloco) + len(linha) + 1 > 1024:
                    e.add_field(name=nome if primeiro else "​", value=bloco, inline=False)
                    bloco, primeiro = "", False
                bloco += linha + "\n"
            e.add_field(name=nome if primeiro else "​", value=bloco, inline=False)
        e.description += "\n🔒 = só para a moderação/administração."
        e.set_footer(text=f"Feito por Harle · {SITE.removeprefix('https://')}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="ping", description="Mostra se o bot está respondendo rápido.")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(embed=embeds.sucesso(f"Pong! {ms} ms"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Geral(bot))
