"""Comunidade: boas-vindas com imagem, sorteios e tickets de suporte."""
import asyncio
import io
import logging
import random
import re
import time
from datetime import datetime, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import embeds, moeda, tempo
from utils.cards import desenhar_boasvindas

log = logging.getLogger("harle.comunidade")

MENSAGEM_PADRAO = "Seja bem-vindo(a), {membro}! Leia as regras e divirta-se. 💙"
MAX_VENCEDORES = 20
DURACAO_MAXIMA_SORTEIO = 30 * 86400


def _formatar_mensagem(modelo: str, membro: discord.Member) -> str:
    return (modelo.replace("{membro}", membro.mention).replace("{nome}", membro.display_name)
            .replace("{servidor}", membro.guild.name).replace("{numero}", str(membro.guild.member_count)))


async def _avatar(membro: discord.abc.User) -> Optional[bytes]:
    try:
        return await membro.display_avatar.replace(size=256, static_format="png").read()
    except (discord.HTTPException, ValueError):
        return None


# ================================ SORTEIO ================================

class BotaoSorteio(discord.ui.DynamicItem[discord.ui.Button], template=r"hsorteio:(?P<id>\d+)"):
    def __init__(self, mensagem_id: int, participantes: int = 0):
        super().__init__(discord.ui.Button(label=f"Participar ({participantes})", emoji="🎉",
                                           style=discord.ButtonStyle.success, custom_id=f"hsorteio:{mensagem_id}"))
        self.mensagem_id = mensagem_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        cog: "Comunidade" = interaction.client.get_cog("Comunidade")
        await cog.clicou_sorteio(interaction, self.mensagem_id)


# ================================ TICKETS ================================

class BotaoAbrirTicket(discord.ui.DynamicItem[discord.ui.Button], template=r"hticket:abrir"):
    def __init__(self):
        super().__init__(discord.ui.Button(label="Abrir ticket", emoji="📩", style=discord.ButtonStyle.primary,
                                           custom_id="hticket:abrir"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        await interaction.client.get_cog("Comunidade").abrir_ticket(interaction)


class BotaoFecharTicket(discord.ui.DynamicItem[discord.ui.Button], template=r"hticket:fechar"):
    def __init__(self):
        super().__init__(discord.ui.Button(label="Fechar ticket", emoji="🔒", style=discord.ButtonStyle.danger,
                                           custom_id="hticket:fechar"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        await interaction.client.get_cog("Comunidade").pedir_fechamento(interaction)


class ConfirmarFechamento(discord.ui.View):
    def __init__(self, cog: "Comunidade"):
        super().__init__(timeout=30)
        self.cog = cog

    @discord.ui.button(label="Sim, fechar", emoji="🔒", style=discord.ButtonStyle.danger)
    async def sim(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content="🔒 Fechando o ticket em 5 segundos...", view=None)
        await self.cog.fechar_ticket(interaction.channel, interaction.user)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def nao(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content="Ok, o ticket continua aberto.", view=None)


# ================================ COG ================================

class Comunidade(commands.Cog, name="Comunidade"):
    boasvindas = app_commands.Group(name="boasvindas", description="Mensagem com imagem para quem entra no servidor.",
                                    guild_only=True, default_permissions=discord.Permissions(manage_guild=True))
    sorteio = app_commands.Group(name="sorteio", description="Sorteios com botão de participar.",
                                 guild_only=True, default_permissions=discord.Permissions(manage_guild=True))
    ticket = app_commands.Group(name="ticket", description="Tickets de suporte (canal privado com a moderação).",
                                guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot):
        self.bot = bot
        self._trava_sorteio = asyncio.Lock()

    @property
    def db(self):
        return self.bot.db

    async def cog_load(self):
        self.bot.add_dynamic_items(BotaoSorteio, BotaoAbrirTicket, BotaoFecharTicket)
        self.verificar_sorteios.start()

    async def cog_unload(self):
        self.verificar_sorteios.cancel()
        self.bot.remove_dynamic_items(BotaoSorteio, BotaoAbrirTicket, BotaoFecharTicket)

    # ============================ BOAS-VINDAS ============================

    async def _enviar_boasvindas(self, membro: discord.Member, canal: discord.abc.Messageable,
                                 mensagem: Optional[str]):
        imagem = await asyncio.to_thread(desenhar_boasvindas, nome=membro.display_name, avatar=await _avatar(membro),
                                         servidor=membro.guild.name, numero=membro.guild.member_count or 0)
        await canal.send(content=_formatar_mensagem(mensagem or MENSAGEM_PADRAO, membro),
                         file=discord.File(imagem, filename="boasvindas.png"),
                         allowed_mentions=discord.AllowedMentions(users=[membro]))

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        if membro.bot:
            return
        config = await self.db.get_welcome(membro.guild.id)
        if not config:
            return
        if config["cargo_id"]:
            cargo = membro.guild.get_role(config["cargo_id"])
            if cargo and cargo < membro.guild.me.top_role:
                try:
                    await membro.add_roles(cargo, reason="Cargo de boas-vindas")
                except discord.HTTPException:
                    pass
        canal = membro.guild.get_channel(config["channel_id"])
        if canal is None:
            return
        try:
            await self._enviar_boasvindas(membro, canal, config["mensagem"])
        except discord.HTTPException as erro:
            log.warning("Boas-vindas falhou em %s: %s", membro.guild.id, erro)

    @boasvindas.command(name="configurar", description="Escolhe o canal e a mensagem de boas-vindas.")
    @app_commands.describe(canal="Onde mandar as boas-vindas",
                           mensagem="Texto. Use {membro}, {nome}, {servidor} e {numero}",
                           cargo="Cargo dado automaticamente a quem entra (opcional)")
    async def bv_configurar(self, interaction: discord.Interaction, canal: discord.TextChannel,
                            mensagem: Optional[app_commands.Range[str, 1, 500]] = None,
                            cargo: Optional[discord.Role] = None):
        perms = canal.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.attach_files):
            return await interaction.response.send_message(
                embed=embeds.erro(f"Preciso de **Enviar mensagens** e **Anexar arquivos** em {canal.mention}."),
                ephemeral=True)
        if cargo and (cargo >= interaction.guild.me.top_role or cargo.managed or cargo.is_default()):
            return await interaction.response.send_message(
                embed=embeds.erro("Não consigo dar esse cargo. Ele precisa estar abaixo do meu."), ephemeral=True)
        await self.db.set_welcome(interaction.guild.id, canal.id, mensagem, cargo.id if cargo else None)
        texto = f"Boas-vindas ligadas em {canal.mention}."
        if cargo:
            texto += f" Quem entrar ganha {cargo.mention}."
        texto += " Use `/boasvindas testar` para ver como fica."
        await interaction.response.send_message(embed=embeds.sucesso(texto), ephemeral=True)

    @boasvindas.command(name="testar", description="Mostra como fica a boas-vindas, usando você como exemplo.")
    async def bv_testar(self, interaction: discord.Interaction):
        config = await self.db.get_welcome(interaction.guild.id)
        await interaction.response.defer(ephemeral=True)
        canal = interaction.guild.get_channel(config["channel_id"]) if config else interaction.channel
        try:
            await self._enviar_boasvindas(interaction.user, canal or interaction.channel,
                                          config["mensagem"] if config else None)
        except discord.HTTPException:
            return await interaction.followup.send(embed=embeds.erro("Não consegui mandar a mensagem nesse canal."),
                                                   ephemeral=True)
        aviso = "" if config else " (ainda não configurada: mandei aqui mesmo)"
        await interaction.followup.send(embed=embeds.sucesso(f"Mensagem de teste enviada{aviso}."), ephemeral=True)

    @boasvindas.command(name="desligar", description="Desliga as boas-vindas.")
    async def bv_desligar(self, interaction: discord.Interaction):
        await self.db.set_welcome(interaction.guild.id, None)
        await interaction.response.send_message(embed=embeds.sucesso("Boas-vindas desligadas."), ephemeral=True)

    # ============================== SORTEIOS ==============================

    def _embed_sorteio(self, dados, participantes: int, vencedores: Optional[List[int]] = None) -> discord.Embed:
        premio = dados["premio"]
        extras = []
        if dados["moedas"]:
            extras.append(f"{moeda.fmt(dados['moedas'])} para cada vencedor")
        if dados["cargo_id"]:
            extras.append(f"cargo <@&{dados['cargo_id']}>")
        termina = datetime.fromtimestamp(dados["termina"], tz=timezone.utc)
        if vencedores is None:
            e = discord.Embed(title=f"🎉 Sorteio: {premio}", color=embeds.AMBAR)
            e.description = (f"Clique em **Participar** para entrar (clique de novo para sair).\n\n"
                             f"⏰ Termina {discord.utils.format_dt(termina, 'R')} "
                             f"({discord.utils.format_dt(termina, 'f')})\n"
                             f"🏆 **{dados['vencedores']}** vencedor(es) · 👥 **{participantes}** participando")
        else:
            e = discord.Embed(title=f"🎉 Sorteio encerrado: {premio}", color=embeds.VERDE if vencedores else embeds.CINZA)
            if vencedores:
                e.description = "🏆 Vencedor(es): " + ", ".join(f"<@{v}>" for v in vencedores)
            else:
                e.description = "Ninguém participou, então não teve vencedor."
            e.description += f"\n👥 {participantes} participaram"
        if extras:
            e.add_field(name="Entregue automaticamente", value="\n".join(extras))
        e.set_footer(text=f"Criado por um moderador · ID {dados['message_id']}")
        return e

    @sorteio.command(name="criar", description="Cria um sorteio com botão de participar.")
    @app_commands.describe(premio="O que vai ser sorteado (texto que aparece)", duracao="Quanto tempo. Ex.: 30m, 2h, 1d",
                           vencedores="Quantas pessoas vão ganhar", canal="Onde postar (padrão: aqui)",
                           moedas=f"{moeda.NOME} entregues para cada vencedor (opcional)",
                           cargo="Cargo entregue para cada vencedor (opcional)")
    async def sorteio_criar(self, interaction: discord.Interaction, premio: app_commands.Range[str, 1, 200],
                            duracao: str, vencedores: app_commands.Range[int, 1, MAX_VENCEDORES] = 1,
                            canal: Optional[discord.TextChannel] = None,
                            moedas: Optional[app_commands.Range[int, 1, 100_000_000]] = None,
                            cargo: Optional[discord.Role] = None):
        prazo = tempo.converter(duracao)
        if prazo is None or prazo.total_seconds() < 30 or prazo.total_seconds() > DURACAO_MAXIMA_SORTEIO:
            return await interaction.response.send_message(
                embed=embeds.erro("Duração inválida. Use algo como `30m`, `2h` ou `1d` (de 30 segundos a 30 dias)."),
                ephemeral=True)
        if cargo and (cargo >= interaction.guild.me.top_role or cargo.managed or cargo.is_default()
                      or cargo.permissions.administrator or cargo.permissions.manage_guild):
            return await interaction.response.send_message(
                embed=embeds.erro("Não posso sortear esse cargo (está acima do meu ou tem permissões de moderação)."),
                ephemeral=True)
        canal = canal or interaction.channel
        termina = int(time.time() + prazo.total_seconds())
        dados = {"premio": premio, "moedas": moedas or 0, "cargo_id": cargo.id if cargo else None,
                 "vencedores": vencedores, "termina": termina, "message_id": 0}
        try:
            mensagem = await canal.send(embed=self._embed_sorteio(dados, 0))
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=embeds.erro(f"Não consigo mandar mensagens em {canal.mention}."), ephemeral=True)
        dados["message_id"] = mensagem.id
        await self.db.sorteio_criar(mensagem.id, interaction.guild.id, canal.id, interaction.user.id, premio,
                                    moedas or 0, cargo.id if cargo else None, vencedores, termina)
        view = discord.ui.View(timeout=None)
        view.add_item(BotaoSorteio(mensagem.id))
        await mensagem.edit(embed=self._embed_sorteio(dados, 0), view=view)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"Sorteio criado em {canal.mention}! ID: `{mensagem.id}`"), ephemeral=True)

    async def clicou_sorteio(self, interaction: discord.Interaction, mensagem_id: int):
        dados = await self.db.sorteio(mensagem_id)
        if dados is None or dados["encerrado"]:
            return await interaction.response.send_message("Esse sorteio já acabou.", ephemeral=True)
        entrou = await self.db.sorteio_entrar(mensagem_id, interaction.user.id)
        total = len(await self.db.sorteio_participantes(mensagem_id))
        view = discord.ui.View(timeout=None)
        view.add_item(BotaoSorteio(mensagem_id, total))
        await interaction.response.edit_message(embed=self._embed_sorteio(dados, total), view=view)
        texto = "🎉 Você está participando! Boa sorte." if entrou else "Você saiu do sorteio."
        await interaction.followup.send(texto, ephemeral=True)

    async def _sortear(self, dados, ja_tinha_vencedor: bool = False) -> List[int]:
        participantes = await self.db.sorteio_participantes(dados["message_id"])
        guild = self.bot.get_guild(dados["guild_id"])
        if guild is not None:
            participantes = [p for p in participantes if guild.get_member(p)]   # ignora quem saiu do servidor
        quantos = 1 if ja_tinha_vencedor else dados["vencedores"]
        vencedores = moeda.sorteio.sample(participantes, min(quantos, len(participantes)))
        for uid in vencedores:
            if dados["moedas"]:
                await self.db.add_coins(dados["guild_id"], uid, dados["moedas"])
            if dados["cargo_id"] and guild:
                cargo, membro = guild.get_role(dados["cargo_id"]), guild.get_member(uid)
                if cargo and membro and cargo < guild.me.top_role:
                    try:
                        await membro.add_roles(cargo, reason="Prêmio de sorteio")
                    except discord.HTTPException:
                        pass
        return vencedores

    async def _encerrar_sorteio(self, dados) -> Optional[List[int]]:
        async with self._trava_sorteio:
            if not await self.db.sorteio_encerrar(dados["message_id"]):
                return None   # já tinha sido encerrado
            vencedores = await self._sortear(dados)
        total = len(await self.db.sorteio_participantes(dados["message_id"]))
        canal = self.bot.get_channel(dados["channel_id"])
        if canal is None:
            return vencedores
        try:
            mensagem = canal.get_partial_message(dados["message_id"])
            await mensagem.edit(embed=self._embed_sorteio(dados, total, vencedores), view=None)
            if vencedores:
                await mensagem.reply(f"🎉 Parabéns {', '.join(f'<@{v}>' for v in vencedores)}! "
                                     f"Vocês ganharam **{dados['premio']}**!",
                                     allowed_mentions=discord.AllowedMentions(users=True))
            else:
                await mensagem.reply("O sorteio acabou sem participantes. 😢")
        except discord.HTTPException as erro:
            log.warning("Não consegui anunciar o sorteio %s: %s", dados["message_id"], erro)
        return vencedores

    @tasks.loop(seconds=20)
    async def verificar_sorteios(self):
        for dados in await self.db.sorteios_vencidos(int(time.time())):
            await self._encerrar_sorteio(dados)

    @verificar_sorteios.before_loop
    async def _antes(self):
        await self.bot.wait_until_ready()

    async def _sorteio_do_servidor(self, interaction: discord.Interaction, mensagem_id: str):
        if not mensagem_id.strip().isdigit():
            await interaction.response.send_message(embed=embeds.erro("Cole o ID do sorteio (aparece no rodapé)."),
                                                    ephemeral=True)
            return None
        dados = await self.db.sorteio(int(mensagem_id))
        if dados is None or dados["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(embed=embeds.erro("Não achei esse sorteio."), ephemeral=True)
            return None
        return dados

    @sorteio.command(name="encerrar", description="Encerra um sorteio agora e sorteia os vencedores.")
    @app_commands.describe(id="ID do sorteio (aparece no rodapé dele)")
    async def sorteio_encerrar(self, interaction: discord.Interaction, id: str):
        dados = await self._sorteio_do_servidor(interaction, id)
        if dados is None:
            return
        if dados["encerrado"]:
            return await interaction.response.send_message(embed=embeds.erro("Esse sorteio já acabou."),
                                                           ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._encerrar_sorteio(dados)
        await interaction.followup.send(embed=embeds.sucesso("Sorteio encerrado."), ephemeral=True)

    @sorteio.command(name="ressortear", description="Sorteia mais um vencedor de um sorteio que já acabou.")
    @app_commands.describe(id="ID do sorteio")
    async def sorteio_ressortear(self, interaction: discord.Interaction, id: str):
        dados = await self._sorteio_do_servidor(interaction, id)
        if dados is None:
            return
        if not dados["encerrado"]:
            return await interaction.response.send_message(
                embed=embeds.erro("Esse sorteio ainda está rolando. Use `/sorteio encerrar`."), ephemeral=True)
        vencedor = await self._sortear(dados, ja_tinha_vencedor=True)
        if not vencedor:
            return await interaction.response.send_message(embed=embeds.erro("Não tem participantes para sortear."),
                                                           ephemeral=True)
        await interaction.response.send_message(
            f"🎉 Novo vencedor de **{dados['premio']}**: <@{vencedor[0]}>!",
            allowed_mentions=discord.AllowedMentions(users=True))

    # ============================== TICKETS ==============================

    @ticket.command(name="painel", description="Cria o painel com o botão de abrir ticket.")
    @app_commands.describe(canal="Onde o painel vai ficar", cargo_suporte="Quem atende os tickets",
                           categoria="Categoria onde os tickets são criados (opcional)",
                           titulo="Título do painel", descricao="Texto do painel")
    async def ticket_painel(self, interaction: discord.Interaction, canal: discord.TextChannel,
                            cargo_suporte: discord.Role, categoria: Optional[discord.CategoryChannel] = None,
                            titulo: Optional[app_commands.Range[str, 1, 200]] = None,
                            descricao: Optional[app_commands.Range[str, 1, 1000]] = None):
        if not interaction.guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                embed=embeds.erro("Preciso da permissão **Gerenciar canais** para criar os tickets."), ephemeral=True)
        await self.db.set_ticket_config(interaction.guild.id, categoria.id if categoria else None, cargo_suporte.id)
        e = discord.Embed(title=titulo or "📩 Precisa de ajuda?", color=embeds.AZUL,
                          description=descricao or "Clique no botão abaixo para abrir um ticket. "
                                                   "Vai ser criado um canal privado entre você e a equipe.")
        view = discord.ui.View(timeout=None)
        view.add_item(BotaoAbrirTicket())
        try:
            await canal.send(embed=e, view=view)
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=embeds.erro(f"Não consigo mandar mensagens em {canal.mention}."), ephemeral=True)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"Painel de tickets criado em {canal.mention}. Atendimento: {cargo_suporte.mention}."),
            ephemeral=True)

    async def abrir_ticket(self, interaction: discord.Interaction):
        guild, membro = interaction.guild, interaction.user
        config = await self.db.get_ticket_config(guild.id)
        if config is None or not config["cargo_id"]:
            return await interaction.response.send_message("Os tickets não estão configurados.", ephemeral=True)
        aberto = await self.db.ticket_aberto_de(guild.id, membro.id)
        if aberto:
            canal = guild.get_channel(aberto["channel_id"])
            if canal:
                return await interaction.response.send_message(f"Você já tem um ticket aberto: {canal.mention}",
                                                               ephemeral=True)
            await self.db.ticket_fechar(aberto["channel_id"])   # o canal foi apagado na mão
        await interaction.response.defer(ephemeral=True)

        suporte = guild.get_role(config["cargo_id"])
        categoria = guild.get_channel(config["categoria_id"]) if config["categoria_id"] else None
        numero = await self.db.ticket_proximo_numero(guild.id)
        permissoes = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membro: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                                read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True,
                                                  read_message_history=True),
        }
        if suporte:
            permissoes[suporte] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                              read_message_history=True)
        nome_canal = f"ticket-{numero:04d}"
        try:
            canal = await guild.create_text_channel(nome_canal, category=categoria, overwrites=permissoes,
                                                    reason=f"Ticket de {membro}")
        except discord.HTTPException:
            return await interaction.followup.send("Não consegui criar o canal do ticket. Avise a moderação.",
                                                   ephemeral=True)
        await self.db.ticket_abrir(canal.id, guild.id, membro.id, numero)

        e = discord.Embed(title=f"📩 Ticket #{numero:04d}", color=embeds.AZUL,
                          description=f"Olá {membro.mention}! Explique o que você precisa e a equipe já vai te atender."
                                      "\nQuando terminar, clique em **Fechar ticket**.")
        view = discord.ui.View(timeout=None)
        view.add_item(BotaoFecharTicket())
        aviso = suporte.mention if suporte else ""
        await canal.send(content=f"{membro.mention} {aviso}", embed=e, view=view,
                         allowed_mentions=discord.AllowedMentions(users=True, roles=True))
        await interaction.followup.send(f"✅ Ticket criado: {canal.mention}", ephemeral=True)

        log_e = discord.Embed(title="📩 Ticket aberto", color=embeds.AZUL, timestamp=embeds.agora())
        log_e.add_field(name="Ticket", value=f"{canal.mention} (#{numero:04d})")
        log_e.add_field(name="Por", value=membro.mention)
        await self.bot.enviar_log(guild, log_e)

    async def pedir_fechamento(self, interaction: discord.Interaction):
        dados = await self.db.ticket(interaction.channel.id)
        if dados is None:
            return await interaction.response.send_message("Esse canal não é um ticket aberto.", ephemeral=True)
        config = await self.db.get_ticket_config(interaction.guild.id)
        do_suporte = any(r.id == (config["cargo_id"] if config else None) for r in interaction.user.roles)
        pode = interaction.user.id == dados["user_id"] or do_suporte or \
            interaction.channel.permissions_for(interaction.user).manage_channels
        if not pode:
            return await interaction.response.send_message("Só quem abriu ou a equipe pode fechar.", ephemeral=True)
        await interaction.response.send_message("Tem certeza que quer fechar o ticket?", view=ConfirmarFechamento(self),
                                                ephemeral=True)

    async def fechar_ticket(self, canal: discord.TextChannel, quem: discord.abc.User):
        dados = await self.db.ticket(canal.id)
        if dados is None:
            return
        await self.db.ticket_fechar(canal.id)
        # transcrição simples em texto, mandada para o canal de registros
        linhas = []
        try:
            async for msg in canal.history(limit=500, oldest_first=True):
                quando = msg.created_at.strftime("%d/%m %H:%M")
                texto = msg.content or ""
                if msg.attachments:
                    texto += " " + " ".join(a.url for a in msg.attachments)
                if msg.embeds and not texto:
                    texto = f"[embed] {msg.embeds[0].title or ''}"
                linhas.append(f"[{quando}] {msg.author}: {texto}")
        except discord.HTTPException:
            pass
        log_e = discord.Embed(title="🔒 Ticket fechado", color=embeds.CINZA, timestamp=embeds.agora())
        log_e.add_field(name="Ticket", value=f"#{dados['numero']:04d}")
        log_e.add_field(name="Aberto por", value=f"<@{dados['user_id']}>")
        log_e.add_field(name="Fechado por", value=quem.mention)
        canal_log_id = await self.db.get_log_channel(canal.guild.id)
        canal_log = canal.guild.get_channel(canal_log_id) if canal_log_id else None
        if canal_log:
            arquivo = discord.File(io.BytesIO("\n".join(linhas).encode("utf-8")),
                                   filename=f"ticket-{dados['numero']:04d}.txt")
            try:
                await canal_log.send(embed=log_e, file=arquivo)
            except discord.HTTPException:
                pass
        await asyncio.sleep(5)
        try:
            await canal.delete(reason=f"Ticket fechado por {quem}")
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Comunidade(bot))
