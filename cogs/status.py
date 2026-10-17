"""Status aleatórios que vão trocando no perfil do bot."""
import random

import discord
from discord.ext import commands, tasks

from utils import moeda

TROCAR_A_CADA = 45  # segundos

# (tipo, texto). Pode usar {servidores}, {membros} e {moeda} no texto.
# Tipos: "jogando", "ouvindo", "assistindo", "competindo" ou "livre" (só o texto, sem prefixo).
STATUS = [
    ("jogando", "/ajuda para ver tudo"),
    ("assistindo", "{servidores} servidores"),
    ("ouvindo", "{membros} pessoas"),
    ("jogando", "quiz com a galera"),
    ("jogando", "jogo da velha (e ganhando)"),
    ("competindo", "o ranking de {moeda}"),
    ("livre", "Já pegou seu /daily hoje?"),
    ("livre", "Feito por Harle 💙"),
    ("assistindo", "harlezinhuu.github.io"),
    ("livre", "Tentando adivinhar a palavra da /forca"),
    ("ouvindo", "o chat para dar XP"),
    ("livre", "Use /trabalhar para ganhar {moeda}"),
    ("assistindo", "a moderação trabalhar"),
]

TIPOS = {
    "jogando": discord.ActivityType.playing,
    "ouvindo": discord.ActivityType.listening,
    "assistindo": discord.ActivityType.watching,
    "competindo": discord.ActivityType.competing,
}


class Status(commands.Cog, name="Status"):
    def __init__(self, bot):
        self.bot = bot
        self._ultimo = None

    async def cog_load(self):
        self.trocar.start()

    async def cog_unload(self):
        self.trocar.cancel()

    def _montar(self) -> discord.BaseActivity:
        opcoes = [s for s in STATUS if s != self._ultimo] or STATUS
        self._ultimo = tipo, texto = random.choice(opcoes)
        texto = texto.format(
            servidores=len(self.bot.guilds),
            membros=f"{sum(g.member_count or 0 for g in self.bot.guilds):,}".replace(",", "."),
            moeda=moeda.NOME,
        )
        if tipo == "livre":
            return discord.CustomActivity(name=texto)
        return discord.Activity(type=TIPOS[tipo], name=texto)

    @tasks.loop(seconds=TROCAR_A_CADA)
    async def trocar(self):
        await self.bot.change_presence(activity=self._montar())

    @trocar.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Status(bot))
