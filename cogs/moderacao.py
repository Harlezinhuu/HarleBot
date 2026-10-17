"""Moderação: banir, expulsar, silenciar, limpar, avisos e controle de canais."""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds, tempo

LIMITE_SILENCIO = timedelta(days=28)  # máximo que o Discord permite


class Moderacao(commands.Cog, name="Moderação"):
    def __init__(self, bot):
        self.bot = bot

    # ---------- ajudantes ----------

    def _checar_hierarquia(self, interaction: discord.Interaction, alvo: discord.Member,
                           checar_bot: bool = True) -> Optional[str]:
        """Devolve o motivo de não poder agir sobre `alvo`, ou None se estiver tudo certo."""
        guild, autor = interaction.guild, interaction.user
        if alvo.id == autor.id:
            return "Você não pode usar isso em você mesmo."
        if alvo.id == self.bot.user.id:
            return "Eu não posso usar isso em mim mesmo."
        if alvo.id == guild.owner_id:
            return "Não dá para punir o dono do servidor."
        if autor.id != guild.owner_id and alvo.top_role >= autor.top_role:
            return "Essa pessoa tem um cargo igual ou acima do seu."
        if checar_bot and alvo.top_role >= guild.me.top_role:
            return ("O cargo dessa pessoa está acima do meu. Suba o cargo do bot em "
                    "Configurações do servidor → Cargos.")
        return None

    @staticmethod
    def _motivo_auditoria(interaction: discord.Interaction, motivo: Optional[str]) -> str:
        """Texto que aparece no Registro de auditoria do Discord."""
        return embeds.cortar(f"{interaction.user} : {motivo or 'Sem motivo informado'}", 512)

    @staticmethod
    async def _avisar_na_dm(usuario: discord.abc.User, guild: discord.Guild, titulo: str,
                            motivo: Optional[str], extra: Optional[Dict[str, str]] = None) -> bool:
        """Manda uma mensagem privada contando o que aconteceu. Se a DM estiver fechada, segue sem erro."""
        e = discord.Embed(title=f"{titulo} em {guild.name}", color=embeds.AMBAR, timestamp=embeds.agora())
        for nome, valor in (extra or {}).items():
            e.add_field(name=nome, value=valor)
        e.add_field(name="Motivo", value=embeds.cortar(motivo or "Sem motivo informado", 1024), inline=False)
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)
        try:
            await usuario.send(embed=e)
            return True
        except discord.HTTPException:
            return False

    async def _registrar(self, interaction: discord.Interaction, acao: str, alvo: discord.abc.User,
                         motivo: Optional[str], extra: Optional[Dict[str, str]] = None) -> discord.Embed:
        """Salva o caso no banco, manda pro canal de registros e devolve o embed."""
        numero = await self.bot.db.add_case(interaction.guild.id, acao, alvo.id, interaction.user.id, motivo)
        e = embeds.caso(acao, alvo, interaction.user, motivo, numero, extra)
        await self.bot.enviar_log(interaction.guild, e)
        return e

    @staticmethod
    async def _recusar(interaction: discord.Interaction, texto: str):
        await interaction.response.send_message(embed=embeds.erro(texto), ephemeral=True)

    # ---------- banir / desbanir ----------

    @app_commands.command(name="banir", description="Bane alguém do servidor (funciona até com quem já saiu).")
    @app_commands.describe(
        usuario="Quem vai ser banido (pode marcar ou colar o ID)",
        motivo="Por que a pessoa está sendo banida",
        apagar_mensagens="Apagar as mensagens recentes dessa pessoa",
    )
    @app_commands.choices(apagar_mensagens=[
        Choice(name="Não apagar", value=0),
        Choice(name="Última hora", value=3600),
        Choice(name="Últimas 24 horas", value=86400),
        Choice(name="Últimos 7 dias", value=604800),
    ])
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def banir(self, interaction: discord.Interaction, usuario: discord.User,
                    motivo: Optional[str] = None, apagar_mensagens: Optional[Choice[int]] = None):
        guild = interaction.guild
        membro = guild.get_member(usuario.id)
        if membro is not None:
            problema = self._checar_hierarquia(interaction, membro)
            if problema:
                return await self._recusar(interaction, problema)

        await interaction.response.defer()
        try:
            await guild.fetch_ban(usuario)
            return await interaction.followup.send(embed=embeds.erro(f"{usuario.mention} já está banido."))
        except discord.NotFound:
            pass

        if membro is not None:
            await self._avisar_na_dm(usuario, guild, "🔨 Você foi banido", motivo)
        await guild.ban(
            usuario,
            reason=self._motivo_auditoria(interaction, motivo),
            delete_message_seconds=apagar_mensagens.value if apagar_mensagens else 0,
        )
        await interaction.followup.send(embed=await self._registrar(interaction, "ban", usuario, motivo))

    @app_commands.command(name="desbanir", description="Tira o banimento de alguém.")
    @app_commands.describe(usuario_id="ID da pessoa banida", motivo="Por que está sendo desbanida")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def desbanir(self, interaction: discord.Interaction, usuario_id: str, motivo: Optional[str] = None):
        if not usuario_id.strip().isdigit():
            return await self._recusar(interaction, "Isso não é um ID válido. Ele é um número, tipo `123456789012345678`.")
        await interaction.response.defer()
        try:
            ban = await interaction.guild.fetch_ban(discord.Object(id=int(usuario_id)))
        except discord.NotFound:
            return await interaction.followup.send(embed=embeds.erro("Essa pessoa não está banida."))
        await interaction.guild.unban(ban.user, reason=self._motivo_auditoria(interaction, motivo))
        await interaction.followup.send(embed=await self._registrar(interaction, "unban", ban.user, motivo))

    # ---------- expulsar ----------

    @app_commands.command(name="expulsar", description="Expulsa alguém do servidor (a pessoa pode voltar com convite).")
    @app_commands.describe(membro="Quem vai ser expulso", motivo="Por que está sendo expulso")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def expulsar(self, interaction: discord.Interaction, membro: discord.Member, motivo: Optional[str] = None):
        problema = self._checar_hierarquia(interaction, membro)
        if problema:
            return await self._recusar(interaction, problema)
        await interaction.response.defer()
        await self._avisar_na_dm(membro, interaction.guild, "👢 Você foi expulso", motivo)
        await membro.kick(reason=self._motivo_auditoria(interaction, motivo))
        await interaction.followup.send(embed=await self._registrar(interaction, "kick", membro, motivo))

    # ---------- silenciar ----------

    @app_commands.command(name="silenciar", description="Deixa alguém sem poder falar por um tempo (castigo).")
    @app_commands.describe(
        membro="Quem vai ser silenciado",
        duracao="Quanto tempo. Ex.: 10m, 1h, 2d, 1h30m (máximo 28d)",
        motivo="Por que está sendo silenciado",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def silenciar(self, interaction: discord.Interaction, membro: discord.Member, duracao: str,
                        motivo: Optional[str] = None):
        problema = self._checar_hierarquia(interaction, membro)
        if problema:
            return await self._recusar(interaction, problema)
        if membro.guild_permissions.administrator:
            return await self._recusar(interaction, "O Discord não deixa silenciar administradores.")
        tempo_total = tempo.converter(duracao)
        if tempo_total is None:
            return await self._recusar(interaction, "Não entendi o tempo. Use algo como `10m`, `1h`, `2d` ou `1h30m`.")
        if tempo_total > LIMITE_SILENCIO:
            return await self._recusar(interaction, "O máximo que o Discord permite é 28 dias (`28d`).")

        await interaction.response.defer()
        termina = embeds.agora() + tempo_total
        extra = {"Duração": tempo.formatar(tempo_total), "Termina": discord.utils.format_dt(termina, "R")}
        await membro.timeout(tempo_total, reason=self._motivo_auditoria(interaction, motivo))
        await self._avisar_na_dm(membro, interaction.guild, "🔇 Você foi silenciado", motivo, extra)
        await interaction.followup.send(embed=await self._registrar(interaction, "timeout", membro, motivo, extra))

    @app_commands.command(name="dessilenciar", description="Tira o silenciamento de alguém antes da hora.")
    @app_commands.describe(membro="Quem vai voltar a poder falar", motivo="Motivo (opcional)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def dessilenciar(self, interaction: discord.Interaction, membro: discord.Member, motivo: Optional[str] = None):
        if not membro.is_timed_out():
            return await self._recusar(interaction, f"{membro.mention} não está silenciado.")
        problema = self._checar_hierarquia(interaction, membro)
        if problema:
            return await self._recusar(interaction, problema)
        await interaction.response.defer()
        await membro.timeout(None, reason=self._motivo_auditoria(interaction, motivo))
        await interaction.followup.send(embed=await self._registrar(interaction, "untimeout", membro, motivo))

    # ---------- limpar mensagens ----------

    @app_commands.command(name="limpar", description="Apaga várias mensagens do canal de uma vez.")
    @app_commands.describe(quantidade="Quantas mensagens apagar (1 a 100)", membro="Apagar só as mensagens dessa pessoa")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def limpar(self, interaction: discord.Interaction, quantidade: app_commands.Range[int, 1, 100],
                     membro: Optional[discord.Member] = None):
        canal = interaction.channel
        if not hasattr(canal, "purge"):
            return await self._recusar(interaction, "Não dá para limpar mensagens nesse tipo de canal.")
        await interaction.response.defer(ephemeral=True)

        contador = 0

        def deve_apagar(mensagem: discord.Message) -> bool:
            nonlocal contador
            if contador >= quantidade:
                return False
            if membro is not None and mensagem.author.id != membro.id:
                return False
            contador += 1
            return True

        # Com filtro de membro, olha mais para trás para achar as mensagens dele
        apagadas = await canal.purge(
            limit=500 if membro else quantidade,
            check=deve_apagar,
            reason=self._motivo_auditoria(interaction, "Limpeza de mensagens"),
        )
        texto = f"{len(apagadas)} mensagens apagadas" + (f" de {membro.mention}." if membro else ".")
        await interaction.followup.send(embed=embeds.sucesso(texto), ephemeral=True)

        log = discord.Embed(title="🧹 Mensagens apagadas", color=embeds.CINZA, timestamp=embeds.agora())
        log.add_field(name="Canal", value=canal.mention)
        log.add_field(name="Moderador", value=interaction.user.mention)
        log.add_field(name="Quantidade", value=str(len(apagadas)))
        if membro:
            log.add_field(name="Só de", value=membro.mention)
        await self.bot.enviar_log(interaction.guild, log)

    # ---------- avisos ----------

    @app_commands.command(name="avisar", description="Dá um aviso para alguém (fica salvo no histórico).")
    @app_commands.describe(membro="Quem vai receber o aviso", motivo="O que a pessoa fez")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def avisar(self, interaction: discord.Interaction, membro: discord.Member, motivo: str):
        problema = self._checar_hierarquia(interaction, membro, checar_bot=False)
        if problema:
            return await self._recusar(interaction, problema)
        await interaction.response.defer()
        db = self.bot.db
        await db.add_warning(interaction.guild.id, membro.id, interaction.user.id, motivo)
        total = len(await db.list_warnings(interaction.guild.id, membro.id))
        extra = {"Total de avisos": str(total)}
        await self._avisar_na_dm(membro, interaction.guild, "⚠️ Você recebeu um aviso", motivo, extra)
        await interaction.followup.send(embed=await self._registrar(interaction, "warn", membro, motivo, extra))

    @app_commands.command(name="avisos", description="Mostra os avisos de alguém.")
    @app_commands.describe(membro="De quem ver os avisos")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def avisos(self, interaction: discord.Interaction, membro: discord.Member):
        lista = await self.bot.db.list_warnings(interaction.guild.id, membro.id)
        if not lista:
            return await interaction.response.send_message(
                embed=embeds.sucesso(f"{membro.mention} não tem nenhum aviso."), ephemeral=True)

        e = discord.Embed(title=f"⚠️ Avisos de {membro.display_name}", color=embeds.AMBAR,
                          description=f"Total: **{len(lista)}**")
        e.set_thumbnail(url=membro.display_avatar.url)
        for aviso in lista[-25:]:  # o Discord aceita até 25 campos
            data = discord.utils.format_dt(_de_timestamp(aviso["created_at"]), "d")
            e.add_field(
                name=f"ID {aviso['id']} · {data}",
                value=embeds.cortar(f"{aviso['reason']}\npor <@{aviso['moderator_id']}>", 1024),
                inline=False,
            )
        if len(lista) > 25:
            e.set_footer(text="Mostrando só os 25 mais recentes.")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="remover-aviso", description="Apaga um aviso específico pelo ID.")
    @app_commands.describe(aviso_id="O ID do aviso (aparece em /avisos)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def remover_aviso(self, interaction: discord.Interaction, aviso_id: int):
        if await self.bot.db.remove_warning(interaction.guild.id, aviso_id):
            await interaction.response.send_message(embed=embeds.sucesso(f"Aviso {aviso_id} removido."), ephemeral=True)
        else:
            await self._recusar(interaction, f"Não achei nenhum aviso com o ID {aviso_id} neste servidor.")

    @app_commands.command(name="limpar-avisos", description="Apaga todos os avisos de alguém.")
    @app_commands.describe(membro="De quem apagar os avisos")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def limpar_avisos(self, interaction: discord.Interaction, membro: discord.Member):
        total = await self.bot.db.clear_warnings(interaction.guild.id, membro.id)
        if total == 0:
            return await self._recusar(interaction, f"{membro.mention} já não tinha avisos.")
        await interaction.response.send_message(
            embed=embeds.sucesso(f"{total} avisos de {membro.mention} apagados."), ephemeral=True)

    # ---------- canais ----------

    @app_commands.command(name="trancar", description="Tranca o canal: ninguém sem permissão consegue mandar mensagem.")
    @app_commands.describe(motivo="Motivo (aparece no canal)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def trancar(self, interaction: discord.Interaction, motivo: Optional[str] = None):
        await self._mudar_tranca(interaction, trancado=True, motivo=motivo)

    @app_commands.command(name="destrancar", description="Destranca o canal.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def destrancar(self, interaction: discord.Interaction):
        await self._mudar_tranca(interaction, trancado=False, motivo=None)

    async def _mudar_tranca(self, interaction: discord.Interaction, trancado: bool, motivo: Optional[str]):
        canal = interaction.channel
        if not isinstance(canal, discord.TextChannel):
            return await self._recusar(interaction, "Isso só funciona em canais de texto.")
        todos = interaction.guild.default_role
        permissoes = canal.overwrites_for(todos)
        if trancado and permissoes.send_messages is False:
            return await self._recusar(interaction, "Esse canal já está trancado.")
        if not trancado and permissoes.send_messages is not False:
            return await self._recusar(interaction, "Esse canal não está trancado.")
        permissoes.send_messages = False if trancado else None
        await canal.set_permissions(todos, overwrite=permissoes,
                                    reason=self._motivo_auditoria(interaction, motivo))
        if trancado:
            e = discord.Embed(title="🔒 Canal trancado", color=embeds.AMBAR,
                              description=motivo or "Só a moderação pode mandar mensagens por enquanto.")
        else:
            e = discord.Embed(title="🔓 Canal destrancado", color=embeds.VERDE,
                              description="Todo mundo pode voltar a conversar.")
        await interaction.response.send_message(embed=e)
        log = e.copy()
        log.add_field(name="Canal", value=canal.mention)
        log.add_field(name="Moderador", value=interaction.user.mention)
        await self.bot.enviar_log(interaction.guild, log)

    @app_commands.command(name="modo-lento", description="Define um intervalo entre as mensagens de cada pessoa no canal.")
    @app_commands.describe(segundos="Intervalo em segundos (0 desliga, máximo 21600 = 6 horas)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def modo_lento(self, interaction: discord.Interaction, segundos: app_commands.Range[int, 0, 21600]):
        canal = interaction.channel
        if not isinstance(canal, (discord.TextChannel, discord.Thread)):
            return await self._recusar(interaction, "Isso só funciona em canais de texto.")
        await canal.edit(slowmode_delay=segundos, reason=self._motivo_auditoria(interaction, "Modo lento"))
        if segundos == 0:
            texto = "Modo lento desligado."
        else:
            texto = f"Modo lento ligado: cada pessoa espera {tempo.formatar(timedelta(seconds=segundos))} entre mensagens."
        await interaction.response.send_message(embed=embeds.sucesso(texto))


def _de_timestamp(segundos: int) -> datetime:
    return datetime.fromtimestamp(segundos, tz=timezone.utc)


async def setup(bot):
    await bot.add_cog(Moderacao(bot))
