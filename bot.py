"""Harle Bot: ponto de entrada.

Rode com:  python bot.py
"""
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from core.db import Database
from utils import embeds

log = logging.getLogger("harle")

# Cada arquivo em cogs/ é um "módulo" do bot. Para desligar um, é só tirar daqui.
COGS = [
    "cogs.geral",
    "cogs.config",
    "cogs.moderacao",
    "cogs.registros",
    "cogs.economia",
    "cogs.niveis",
    "cogs.jogos",
    "cogs.cassino",
    "cogs.batalha",
    "cogs.status",
]

# Nome das permissões como aparecem no Discord em português
PERMISSOES_PT = {
    "ban_members": "Banir membros",
    "kick_members": "Expulsar membros",
    "moderate_members": "Castigar membros",
    "manage_messages": "Gerenciar mensagens",
    "manage_channels": "Gerenciar canais",
    "manage_roles": "Gerenciar cargos",
    "manage_guild": "Gerenciar servidor",
    "read_message_history": "Ler histórico de mensagens",
    "send_messages": "Enviar mensagens",
    "embed_links": "Inserir links",
}


def _nomes(perms):
    return ", ".join(PERMISSOES_PT.get(p, p) for p in perms)


class HarleBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # entrada/saída de membros
        intents.message_content = True  # registrar mensagens apagadas/editadas
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.db = Database(os.getenv("DB_PATH") or "data/harle.db")
        self.tree.on_error = self.erro_de_comando

    async def setup_hook(self):
        await self.db.connect()
        for cog in COGS:
            await self.load_extension(cog)

        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            # Servidor de testes: os comandos aparecem na hora
            servidor = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=servidor)
            try:
                sincronizados = await self.tree.sync(guild=servidor)
            except discord.Forbidden:
                log.error(
                    "Não consegui registrar os comandos no servidor %s. Confira se: "
                    "(1) o GUILD_ID é o ID certo do servidor; "
                    "(2) o bot já foi adicionado nesse servidor; "
                    "(3) o convite foi gerado com os escopos 'bot' E 'applications.commands'. "
                    "O bot vai continuar ligado, mas os comandos não vão aparecer até isso ser resolvido.",
                    guild_id,
                )
                return
        else:
            # Global: pode levar alguns minutos para aparecer em todos os servidores
            sincronizados = await self.tree.sync()
        log.info("%d comandos sincronizados", len(sincronizados))

    async def on_ready(self):
        log.info("Online como %s (%s) em %d servidores", self.user, self.user.id, len(self.guilds))

    async def close(self):
        await self.db.close()
        await super().close()

    async def enviar_log(self, guild: discord.Guild, embed: discord.Embed):
        """Manda um registro para o canal de logs do servidor, se houver um configurado."""
        canal_id = await self.db.get_log_channel(guild.id)
        if not canal_id:
            return
        canal = guild.get_channel(canal_id)
        if canal is None:
            return
        try:
            await canal.send(embed=embed)
        except discord.HTTPException:
            log.warning("Não consegui enviar log no canal %s do servidor %s", canal_id, guild.id)

    async def erro_de_comando(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            texto = f"Você precisa da permissão **{_nomes(error.missing_permissions)}** para usar isso."
        elif isinstance(error, app_commands.BotMissingPermissions):
            texto = f"Eu preciso da permissão **{_nomes(error.missing_permissions)}** para fazer isso."
        elif isinstance(error, app_commands.NoPrivateMessage):
            texto = "Esse comando só funciona dentro de um servidor."
        elif isinstance(error, app_commands.TransformerError):
            texto = "Não encontrei isso que você colocou. Confira se o usuário ou canal existe."
        elif isinstance(error, app_commands.CommandOnCooldown):
            texto = f"Calma! Tente de novo em {error.retry_after:.0f} segundos."
        elif isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
            texto = ("O Discord não me deixou fazer isso. Confira se o meu cargo está acima do cargo "
                     "da pessoa e se eu tenho as permissões necessárias.")
        else:
            log.exception("Erro no comando /%s", interaction.command.name if interaction.command else "?",
                          exc_info=error)
            texto = "Deu um erro inesperado. Ele ficou registrado no console do bot."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embeds.erro(texto), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embeds.erro(texto), ephemeral=True)
        except discord.HTTPException:
            pass


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Falta o DISCORD_TOKEN. Copie o .env.example para .env e cole o token do seu bot lá.")
    HarleBot().run(token, log_handler=None)


if __name__ == "__main__":
    main()
