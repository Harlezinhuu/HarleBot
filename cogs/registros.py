"""Registra no canal de logs: mensagens apagadas/editadas e entradas/saídas de membros."""
import discord
from discord.ext import commands

from utils import embeds


class Registros(commands.Cog, name="Registros"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, mensagem: discord.Message):
        if mensagem.guild is None or mensagem.author.bot:
            return
        e = discord.Embed(title="🗑️ Mensagem apagada", color=embeds.CINZA, timestamp=embeds.agora())
        e.set_author(name=str(mensagem.author), icon_url=mensagem.author.display_avatar.url)
        e.add_field(name="Canal", value=mensagem.channel.mention)
        e.add_field(name="Autor", value=mensagem.author.mention)
        e.add_field(name="Conteúdo", value=embeds.cortar(mensagem.content) or "*(sem texto)*", inline=False)
        if mensagem.attachments:
            e.add_field(name="Anexos", value=str(len(mensagem.attachments)))
        await self.bot.enviar_log(mensagem.guild, e)

    @commands.Cog.listener()
    async def on_message_edit(self, antes: discord.Message, depois: discord.Message):
        if depois.guild is None or depois.author.bot or antes.content == depois.content:
            return
        e = discord.Embed(title="✏️ Mensagem editada", color=embeds.AZUL, timestamp=embeds.agora(),
                          description=f"[Ir para a mensagem]({depois.jump_url})")
        e.set_author(name=str(depois.author), icon_url=depois.author.display_avatar.url)
        e.add_field(name="Canal", value=depois.channel.mention)
        e.add_field(name="Autor", value=depois.author.mention)
        e.add_field(name="Antes", value=embeds.cortar(antes.content) or "*(sem texto)*", inline=False)
        e.add_field(name="Depois", value=embeds.cortar(depois.content) or "*(sem texto)*", inline=False)
        await self.bot.enviar_log(depois.guild, e)

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        e = discord.Embed(title="📥 Entrou no servidor", color=embeds.VERDE, timestamp=embeds.agora(),
                          description=f"{membro.mention} `{membro}`")
        e.add_field(name="Conta criada", value=discord.utils.format_dt(membro.created_at, "R"))
        e.add_field(name="Membros agora", value=str(membro.guild.member_count))
        e.set_thumbnail(url=membro.display_avatar.url)
        await self.bot.enviar_log(membro.guild, e)

    @commands.Cog.listener()
    async def on_member_remove(self, membro: discord.Member):
        e = discord.Embed(title="📤 Saiu do servidor", color=embeds.VERMELHO, timestamp=embeds.agora(),
                          description=f"{membro.mention} `{membro}`")
        if membro.joined_at:
            e.add_field(name="Estava desde", value=discord.utils.format_dt(membro.joined_at, "R"))
        e.set_thumbnail(url=membro.display_avatar.url)
        await self.bot.enviar_log(membro.guild, e)


async def setup(bot):
    await bot.add_cog(Registros(bot))
