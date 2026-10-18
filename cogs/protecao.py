"""Proteção do servidor: automod (spam, links, convites, CAPS, menções, palavras) e anti-raid."""
import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Deque, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds
from utils.protecao import ContadorDeInfracoes, DetectorDeRaid, DetectorDeSpam, analisar_mensagem

log = logging.getLogger("harle.protecao")

INFRACOES_PARA_SILENCIAR = 3
TEMPO_SILENCIO = timedelta(minutes=10)
DURACAO_RAID = 600  # segundos que o modo anti-raid fica ligado
PUNICOES = {"apagar": "Só apagar a mensagem", "avisar": "Apagar e dar um aviso (/avisos)",
            "silenciar": f"Apagar e silenciar na {INFRACOES_PARA_SILENCIAR}ª vez em 10 min"}
ACOES_RAID = {"verificacao": "Subir a verificação do servidor para o máximo",
              "expulsar": "Expulsar quem entrar durante o ataque"}


def _sim_nao(valor) -> str:
    return "✅" if valor else "❌"


class Protecao(commands.Cog, name="Proteção"):
    automod = app_commands.Group(name="automod", description="Moderação automática do chat.",
                                 guild_only=True, default_permissions=discord.Permissions(manage_guild=True))
    antiraid = app_commands.Group(name="antiraid", description="Proteção contra raids (muita gente entrando de uma vez).",
                                  guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot):
        self.bot = bot
        self.spam = DetectorDeSpam()
        self.infracoes = ContadorDeInfracoes()
        self.raid = DetectorDeRaid()
        self.em_raid: Dict[int, float] = {}                 # guild -> quando o modo raid termina
        self.verificacao_antes: Dict[int, discord.VerificationLevel] = {}
        self.entradas_recentes: Dict[int, Deque[Tuple[float, int]]] = defaultdict(lambda: deque(maxlen=100))
        self._cache: Dict[int, Tuple[float, Dict, List[str], List[int]]] = {}

    @property
    def db(self):
        return self.bot.db

    async def _config(self, guild_id: int):
        """Configuração do automod com cache de 30s (evita ir no banco a cada mensagem)."""
        agora = time.monotonic()
        guardado = self._cache.get(guild_id)
        if guardado and agora - guardado[0] < 30:
            return guardado[1:]
        dados = (await self.db.get_automod(guild_id), await self.db.palavras_proibidas(guild_id),
                 await self.db.ignorados(guild_id))
        self._cache[guild_id] = (agora, *dados)
        return dados

    def _limpar_cache(self, guild_id: int):
        self._cache.pop(guild_id, None)

    # ================================ AUTOMOD ================================

    @commands.Cog.listener()
    async def on_message(self, mensagem: discord.Message):
        if mensagem.guild is None or mensagem.author.bot or not isinstance(mensagem.author, discord.Member):
            return
        autor = mensagem.author
        perms = mensagem.channel.permissions_for(autor)
        if perms.manage_messages or perms.administrator:
            return  # a moderação não é afetada
        config, proibidas, ignorados = await self._config(mensagem.guild.id)
        if not config["ativo"]:
            return
        if mensagem.channel.id in ignorados or getattr(mensagem.channel, "category_id", None) in ignorados \
                or any(c.id in ignorados for c in autor.roles):
            return

        motivo = None
        if config["anti_spam"] and self.spam.registrar(mensagem.guild.id, autor.id, mensagem.content):
            motivo = "spam"
        if motivo is None:
            mencoes = len(mensagem.raw_mentions) + len(mensagem.raw_role_mentions) + int(mensagem.mention_everyone)
            motivo = analisar_mensagem(mensagem.content, mencoes, config, proibidas)
        if motivo:
            await self._punir(mensagem, motivo, config["punicao"])

    async def _punir(self, mensagem: discord.Message, motivo: str, punicao: str):
        autor, guild = mensagem.author, mensagem.guild
        try:
            await mensagem.delete()
        except discord.HTTPException:
            pass
        vezes = self.infracoes.somar(guild.id, autor.id)
        extra = ""

        if punicao == "avisar":
            await self.db.add_warning(guild.id, autor.id, self.bot.user.id, f"Automod: {motivo}")
            extra = " Você recebeu um aviso."
        elif punicao == "silenciar" and vezes >= INFRACOES_PARA_SILENCIAR:
            if guild.me.guild_permissions.moderate_members and autor.top_role < guild.me.top_role:
                try:
                    await autor.timeout(TEMPO_SILENCIO, reason=f"Automod: {vezes} infrações ({motivo})")
                    extra = " Você foi silenciado por 10 minutos."
                    self.infracoes.zerar(guild.id, autor.id)
                except discord.HTTPException:
                    pass

        try:
            await mensagem.channel.send(f"🛡️ {autor.mention}, sua mensagem foi apagada: **{motivo}**.{extra}",
                                        delete_after=8, allowed_mentions=discord.AllowedMentions(users=[autor]))
        except discord.HTTPException:
            pass

        e = discord.Embed(title="🛡️ Automod", color=embeds.AMBAR, timestamp=embeds.agora())
        e.add_field(name="Membro", value=f"{autor.mention} `{autor}`")
        e.add_field(name="Canal", value=mensagem.channel.mention)
        e.add_field(name="Motivo", value=motivo)
        if extra:
            e.add_field(name="Punição", value=extra.strip())
        if mensagem.content:
            e.add_field(name="Mensagem", value=embeds.cortar(mensagem.content), inline=False)
        await self.bot.enviar_log(guild, e)

    @automod.command(name="configurar", description="Liga o automod e escolhe o que ele bloqueia.")
    @app_commands.describe(ativo="Ligar ou desligar o automod", spam="Bloquear spam (muitas mensagens ou repetidas)",
                           links="Bloquear links", convites="Bloquear convites de outros servidores",
                           maiusculas="Bloquear mensagens em CAPS LOCK", mencoes="Bloquear excesso de menções",
                           limite_mencoes="Quantas menções numa mensagem já é excesso",
                           punicao="O que fazer com quem quebrar as regras")
    @app_commands.choices(punicao=[Choice(name=v, value=k) for k, v in PUNICOES.items()])
    async def automod_configurar(self, interaction: discord.Interaction, ativo: Optional[bool] = None,
                                 spam: Optional[bool] = None, links: Optional[bool] = None,
                                 convites: Optional[bool] = None, maiusculas: Optional[bool] = None,
                                 mencoes: Optional[bool] = None,
                                 limite_mencoes: Optional[app_commands.Range[int, 2, 50]] = None,
                                 punicao: Optional[Choice[str]] = None):
        await self.db.set_automod(interaction.guild.id, ativo=ativo, anti_spam=spam, anti_links=links,
                                  anti_convites=convites, anti_caps=maiusculas, anti_mencoes=mencoes,
                                  limite_mencoes=limite_mencoes, punicao=punicao.value if punicao else None)
        self._limpar_cache(interaction.guild.id)
        await interaction.response.send_message(embed=await self._embed_automod(interaction.guild), ephemeral=True)

    @automod.command(name="ver", description="Mostra como o automod está configurado.")
    async def automod_ver(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=await self._embed_automod(interaction.guild), ephemeral=True)

    async def _embed_automod(self, guild: discord.Guild) -> discord.Embed:
        c = await self.db.get_automod(guild.id)
        palavras = await self.db.palavras_proibidas(guild.id)
        ignorados = await self.db.ignorados(guild.id)
        e = discord.Embed(title=f"🛡️ Automod {'ligado' if c['ativo'] else 'desligado'}",
                          color=embeds.VERDE if c["ativo"] else embeds.CINZA)
        e.add_field(name="Bloqueia", value="\n".join([
            f"{_sim_nao(c['anti_spam'])} Spam", f"{_sim_nao(c['anti_links'])} Links",
            f"{_sim_nao(c['anti_convites'])} Convites", f"{_sim_nao(c['anti_caps'])} CAPS LOCK",
            f"{_sim_nao(c['anti_mencoes'])} {c['limite_mencoes']} ou mais menções",
        ]))
        e.add_field(name="Punição", value=PUNICOES[c["punicao"]])
        e.add_field(name=f"Palavras proibidas ({len(palavras)})",
                    value=embeds.cortar(", ".join(f"||{p}||" for p in palavras) or "nenhuma", 1024), inline=False)
        nomes = []
        for alvo in ignorados:
            obj = guild.get_channel(alvo) or guild.get_role(alvo)
            nomes.append(obj.mention if obj else f"`{alvo}`")
        e.add_field(name="Ignorados", value=", ".join(nomes) or "nenhum", inline=False)
        e.set_footer(text="Quem tem permissão de Gerenciar mensagens nunca é afetado.")
        if not c["ativo"]:
            e.description = "Use `/automod configurar ativo: True` para ligar."
        return e

    @automod.command(name="palavra", description="Adiciona ou tira uma palavra proibida.")
    @app_commands.describe(acao="Adicionar ou remover", palavra="A palavra ou expressão")
    @app_commands.choices(acao=[Choice(name="Adicionar", value="adicionar"), Choice(name="Remover", value="remover")])
    async def automod_palavra(self, interaction: discord.Interaction, acao: Choice[str],
                              palavra: app_commands.Range[str, 2, 60]):
        palavra = palavra.strip().lower()
        if acao.value == "adicionar":
            await self.db.palavra_adicionar(interaction.guild.id, palavra)
            texto = f"||{palavra}|| agora é proibida."
        elif await self.db.palavra_remover(interaction.guild.id, palavra):
            texto = f"||{palavra}|| foi liberada."
        else:
            return await interaction.response.send_message(embed=embeds.erro("Essa palavra não estava na lista."),
                                                           ephemeral=True)
        self._limpar_cache(interaction.guild.id)
        await interaction.response.send_message(embed=embeds.sucesso(texto), ephemeral=True)

    @automod.command(name="ignorar", description="Faz o automod ignorar (ou voltar a vigiar) um canal ou cargo.")
    @app_commands.describe(canal="Canal ou categoria para ignorar", cargo="Cargo para ignorar")
    async def automod_ignorar(self, interaction: discord.Interaction,
                              canal: Optional[discord.abc.GuildChannel] = None, cargo: Optional[discord.Role] = None):
        alvo = canal or cargo
        if alvo is None:
            return await interaction.response.send_message(embed=embeds.erro("Escolha um canal ou um cargo."),
                                                           ephemeral=True)
        agora_ignora = await self.db.alternar_ignorado(interaction.guild.id, alvo.id)
        self._limpar_cache(interaction.guild.id)
        texto = f"O automod vai **ignorar** {alvo.mention}." if agora_ignora else \
            f"O automod voltou a vigiar {alvo.mention}."
        await interaction.response.send_message(embed=embeds.sucesso(texto), ephemeral=True)

    # ================================ ANTI-RAID ================================

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        guild = membro.guild
        config = await self.db.get_antiraid(guild.id)
        if not config["ativo"]:
            return
        agora = time.monotonic()

        # contas novas demais (contas "fake" criadas para raid)
        if config["idade_minima"] > 0:
            idade = discord.utils.utcnow() - membro.created_at
            if idade < timedelta(days=config["idade_minima"]):
                await self._expulsar(membro, f"Conta com menos de {config['idade_minima']} dias (anti-raid)")
                return

        self.entradas_recentes[guild.id].append((agora, membro.id))
        if guild.id in self.em_raid:
            if config["acao"] == "expulsar":
                await self._expulsar(membro, "Entrou durante um raid")
            return
        if self.raid.registrar(guild.id, config["limite"], config["janela"]):
            await self._iniciar_raid(guild, config)

    async def _expulsar(self, membro: discord.Member, motivo: str):
        if not membro.guild.me.guild_permissions.kick_members:
            return
        try:
            await membro.send(f"Você foi removido de **{membro.guild.name}** pela proteção automática: {motivo}. "
                              "Se foi um engano, tente entrar de novo mais tarde.")
        except discord.HTTPException:
            pass
        try:
            await membro.kick(reason=motivo)
        except discord.HTTPException:
            pass

    async def _iniciar_raid(self, guild: discord.Guild, config: Dict):
        self.em_raid[guild.id] = time.monotonic() + DURACAO_RAID
        feito = []
        if config["acao"] == "verificacao" and guild.me.guild_permissions.manage_guild:
            self.verificacao_antes[guild.id] = guild.verification_level
            try:
                await guild.edit(verification_level=discord.VerificationLevel.highest, reason="Anti-raid")
                feito.append("verificação do servidor no máximo")
            except discord.HTTPException:
                pass
        elif config["acao"] == "expulsar":
            limite = time.monotonic() - config["janela"]
            for momento, uid in list(self.entradas_recentes[guild.id]):
                membro = guild.get_member(uid)
                if momento >= limite and membro:
                    await self._expulsar(membro, "Entrou durante um raid")
            feito.append("expulsando quem entrar")

        e = discord.Embed(title="🚨 Raid detectado!", color=embeds.VERMELHO, timestamp=embeds.agora(),
                          description=f"Mais de {config['limite'] - 1} pessoas entraram em {config['janela']} segundos.")
        e.add_field(name="O que eu fiz", value=", ".join(feito) or "nada (falta permissão)")
        e.add_field(name="Duração", value=f"{DURACAO_RAID // 60} minutos (ou até `/antiraid encerrar`)")
        await self.bot.enviar_log(guild, e)
        log.warning("Raid detectado em %s", guild.id)
        asyncio.create_task(self._encerrar_depois(guild))

    async def _encerrar_depois(self, guild: discord.Guild):
        while guild.id in self.em_raid:
            falta = self.em_raid[guild.id] - time.monotonic()
            if falta <= 0:
                await self._encerrar_raid(guild)
                return
            await asyncio.sleep(min(falta, 30))

    async def _encerrar_raid(self, guild: discord.Guild) -> bool:
        if self.em_raid.pop(guild.id, None) is None:
            return False
        self.raid.limpar(guild.id)
        anterior = self.verificacao_antes.pop(guild.id, None)
        if anterior is not None:
            try:
                await guild.edit(verification_level=anterior, reason="Fim do anti-raid")
            except discord.HTTPException:
                pass
        await self.bot.enviar_log(guild, discord.Embed(title="✅ Modo anti-raid encerrado", color=embeds.VERDE,
                                                       timestamp=embeds.agora()))
        return True

    @antiraid.command(name="configurar", description="Liga o anti-raid e define quando ele deve agir.")
    @app_commands.describe(ativo="Ligar ou desligar", limite="Quantas entradas contam como raid",
                           segundos="Em quantos segundos", acao="O que fazer quando detectar um raid",
                           idade_minima="Expulsar contas criadas há menos de X dias (0 = desligado)")
    @app_commands.choices(acao=[Choice(name=v, value=k) for k, v in ACOES_RAID.items()])
    async def antiraid_configurar(self, interaction: discord.Interaction, ativo: Optional[bool] = None,
                                  limite: Optional[app_commands.Range[int, 3, 100]] = None,
                                  segundos: Optional[app_commands.Range[int, 5, 300]] = None,
                                  acao: Optional[Choice[str]] = None,
                                  idade_minima: Optional[app_commands.Range[int, 0, 60]] = None):
        await self.db.set_antiraid(interaction.guild.id, ativo=ativo, limite=limite, janela=segundos,
                                   acao=acao.value if acao else None, idade_minima=idade_minima)
        c = await self.db.get_antiraid(interaction.guild.id)
        e = discord.Embed(title=f"🚨 Anti-raid {'ligado' if c['ativo'] else 'desligado'}",
                          color=embeds.VERDE if c["ativo"] else embeds.CINZA)
        e.add_field(name="Detecta", value=f"{c['limite']} entradas em {c['janela']} segundos")
        e.add_field(name="Ação", value=ACOES_RAID[c["acao"]])
        e.add_field(name="Contas novas", value=f"expulsa com menos de {c['idade_minima']} dias"
                    if c["idade_minima"] else "permitidas")
        faltando = []
        me = interaction.guild.me.guild_permissions
        if c["acao"] == "verificacao" and not me.manage_guild:
            faltando.append("Gerenciar servidor")
        if (c["acao"] == "expulsar" or c["idade_minima"]) and not me.kick_members:
            faltando.append("Expulsar membros")
        if faltando:
            e.add_field(name="⚠️ Falta permissão", value=", ".join(faltando), inline=False)
        e.set_footer(text="Os avisos aparecem no canal de registros (/config-logs).")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @antiraid.command(name="encerrar", description="Encerra agora o modo anti-raid e volta tudo ao normal.")
    async def antiraid_encerrar(self, interaction: discord.Interaction):
        if await self._encerrar_raid(interaction.guild):
            await interaction.response.send_message(embed=embeds.sucesso("Modo anti-raid encerrado."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.erro("Não tem nenhum raid em andamento."),
                                                    ephemeral=True)


async def setup(bot):
    await bot.add_cog(Protecao(bot))
