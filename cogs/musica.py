"""Música: toca SoundCloud e YouTube no canal de voz, com fila, loop e volume."""
import asyncio
import logging
import random
import time
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds
from utils.musica import Faixa, achar_ffmpeg, buscar, extrair_stream, formatar_duracao, opcoes_ffmpeg_antes

log = logging.getLogger("harle.musica")

FFMPEG = achar_ffmpeg()
FFMPEG_ANTES = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
FFMPEG_OPCOES = "-vn"
SAIR_SEM_MUSICA = 180   # segundos parado sem nada na fila
SAIR_SOZINHO = 60       # segundos sozinho no canal
LIMITE_FILA = 200
LOOPS = {"desligado": "➡️ Desligado", "musica": "🔂 Música atual", "fila": "🔁 Fila inteira"}
COR = 0xFF5500  # laranja SoundCloud


class Tocador:
    """Um tocador por servidor."""

    def __init__(self, bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.fila: List[Faixa] = []
        self.atual: Optional[Faixa] = None
        self.loop = "desligado"
        self.volume = 0.5
        self.canal_texto: Optional[discord.abc.Messageable] = None
        self.inicio = 0.0
        self.pausado_em: Optional[float] = None
        self._timer_saida: Optional[asyncio.Task] = None
        self._pulando = False
        self.parando = False

    @property
    def vc(self) -> Optional[discord.VoiceClient]:
        return self.guild.voice_client

    @property
    def tocando(self) -> bool:
        return bool(self.vc and (self.vc.is_playing() or self.vc.is_paused()))

    def tempo_atual(self) -> int:
        if not self.atual:
            return 0
        fim = self.pausado_em or time.monotonic()
        return int(fim - self.inicio)

    # ----- saída automática -----

    def agendar_saida(self, segundos: int, motivo: str):
        self.cancelar_saida()
        self._timer_saida = asyncio.create_task(self._sair_depois(segundos, motivo))

    def cancelar_saida(self):
        if self._timer_saida and not self._timer_saida.done():
            self._timer_saida.cancel()
        self._timer_saida = None

    async def _sair_depois(self, segundos: int, motivo: str):
        try:
            await asyncio.sleep(segundos)
        except asyncio.CancelledError:
            return
        estava_conectado = bool(self.vc)
        await self.parar()
        if estava_conectado:
            await self.avisar(f"👋 Saí do canal de voz {motivo}.")

    async def avisar(self, texto: str = None, embed: discord.Embed = None):
        if self.canal_texto:
            try:
                await self.canal_texto.send(content=texto, embed=embed)
            except discord.HTTPException:
                pass

    # ----- tocar -----

    async def tocar_proxima(self):
        if self.parando or not self.vc or not self.vc.is_connected():
            return
        anterior = self.atual
        if anterior and not self._pulando:
            if self.loop == "musica":
                self.fila.insert(0, anterior)
            elif self.loop == "fila":
                self.fila.append(anterior)
        self._pulando = False

        while self.fila:
            faixa = self.fila.pop(0)
            try:
                faixa = await self._preparar(faixa)
            except Exception as erro:
                log.warning("Falha ao tocar %s: %s", faixa.pagina, erro)
                await self.avisar(embed=embeds.erro(f"Não consegui tocar **{faixa.titulo}**. Pulando..."))
                continue

            fonte = discord.FFmpegPCMAudio(faixa.stream, executable=FFMPEG,
                                           before_options=opcoes_ffmpeg_antes(FFMPEG_ANTES, faixa.headers),
                                           options=FFMPEG_OPCOES)
            audio = discord.PCMVolumeTransformer(fonte, volume=self.volume)
            self.atual = faixa
            self.inicio, self.pausado_em = time.monotonic(), None
            self.cancelar_saida()
            loop = asyncio.get_running_loop()
            self.vc.play(audio, after=lambda e: loop.call_soon_threadsafe(self._terminou, e))
            if not (self.loop == "musica" and anterior is faixa):
                await self.avisar(embed=self.embed_tocando("🎶 Tocando agora"))
            return

        self.atual = None
        self.agendar_saida(SAIR_SEM_MUSICA, "porque a fila acabou")

    async def _preparar(self, faixa: Faixa) -> Faixa:
        """Busca o áudio. Se o YouTube bloquear, procura a mesma música no SoundCloud."""
        try:
            return await asyncio.to_thread(extrair_stream, faixa)
        except Exception:
            if faixa.fonte != "YouTube":
                raise
            alternativas = await asyncio.to_thread(buscar, faixa.titulo, "soundcloud", faixa.pedido_por)
            if not alternativas:
                raise
            await self.avisar(f"↪️ O YouTube não liberou **{faixa.titulo}**, tocando a versão do SoundCloud.")
            return await asyncio.to_thread(extrair_stream, alternativas[0])

    def _terminou(self, erro: Optional[Exception]):
        if erro:
            log.warning("Erro no áudio: %s", erro)
        asyncio.create_task(self.tocar_proxima())

    def pular(self):
        self._pulando = self.loop == "musica"  # pular com loop de música vai para a próxima de verdade
        if self.vc:
            self.vc.stop()  # o "after" chama a próxima

    async def parar(self):
        self.parando = True
        self.fila.clear()
        self.atual = None
        self.cancelar_saida()
        if self.vc:
            self.vc.stop()
            await self.vc.disconnect(force=True)

    def embed_tocando(self, titulo: str) -> discord.Embed:
        f = self.atual
        e = discord.Embed(title=titulo, description=f"**[{f.titulo}]({f.pagina})**", color=COR)
        e.add_field(name="Duração", value=formatar_duracao(f.duracao))
        e.add_field(name="Fonte", value=f.fonte)
        e.add_field(name="Pedido por", value=f"<@{f.pedido_por}>")
        if self.fila:
            e.set_footer(text=f"{len(self.fila)} na fila · loop: {LOOPS[self.loop]}")
        if f.thumb:
            e.set_thumbnail(url=f.thumb)
        return e


class Musica(commands.Cog, name="Música"):
    def __init__(self, bot):
        self.bot = bot
        self.tocadores: Dict[int, Tocador] = {}

    def tocador(self, guild: discord.Guild) -> Tocador:
        if guild.id not in self.tocadores:
            self.tocadores[guild.id] = Tocador(self.bot, guild)
        return self.tocadores[guild.id]

    async def cog_unload(self):
        for t in self.tocadores.values():
            await t.parar()

    # ----- verificações -----

    @staticmethod
    async def _erro(interaction: discord.Interaction, texto: str):
        if interaction.response.is_done():
            await interaction.followup.send(embed=embeds.erro(texto), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.erro(texto), ephemeral=True)

    async def _no_mesmo_canal(self, interaction: discord.Interaction, precisa_tocar: bool = True) -> Optional[Tocador]:
        t = self.tocador(interaction.guild)
        voz = interaction.user.voice
        if not t.vc:
            await self._erro(interaction, "Não estou tocando nada agora.")
            return None
        if not voz or voz.channel != t.vc.channel:
            await self._erro(interaction, f"Entre no canal {t.vc.channel.mention} para controlar a música.")
            return None
        if precisa_tocar and not t.atual:
            await self._erro(interaction, "Não estou tocando nada agora.")
            return None
        return t

    # ----- comandos -----

    @app_commands.command(name="tocar", description="Toca uma música (nome ou link do YouTube/SoundCloud).")
    @app_commands.describe(busca="Nome da música ou link (playlists também)", fonte="Onde procurar quando é pelo nome")
    @app_commands.choices(fonte=[Choice(name="YouTube", value="youtube"), Choice(name="SoundCloud", value="soundcloud")])
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3)
    async def tocar(self, interaction: discord.Interaction, busca: str, fonte: Optional[Choice[str]] = None):
        voz = interaction.user.voice
        if not voz or not voz.channel:
            return await self._erro(interaction, "Entre num canal de voz primeiro.")
        t = self.tocador(interaction.guild)
        if t.vc and t.vc.channel != voz.channel and t.tocando:
            return await self._erro(interaction, f"Já estou tocando em {t.vc.channel.mention}.")
        perms = voz.channel.permissions_for(interaction.guild.me)
        if not (perms.connect and perms.speak):
            return await self._erro(interaction, f"Não tenho permissão para entrar e falar em {voz.channel.mention}.")
        if len(t.fila) >= LIMITE_FILA:
            return await self._erro(interaction, f"A fila está cheia ({LIMITE_FILA} músicas).")

        await interaction.response.defer()
        onde = fonte.value if fonte else "youtube"
        try:
            faixas = await asyncio.to_thread(buscar, busca, onde, interaction.user.id)
            if not faixas and onde == "youtube":
                faixas = await asyncio.to_thread(buscar, busca, "soundcloud", interaction.user.id)
        except Exception as erro:
            log.warning("Busca falhou (%s): %s", busca, erro)
            faixas = []
            if onde == "youtube":
                try:
                    faixas = await asyncio.to_thread(buscar, busca, "soundcloud", interaction.user.id)
                except Exception:
                    pass
        if not faixas:
            return await interaction.followup.send(embed=embeds.erro("Não encontrei nada com essa busca."))

        if not t.vc:
            try:
                await voz.channel.connect(self_deaf=True)
            except Exception as erro:
                log.warning("Não conectei na voz: %s", erro)
                return await interaction.followup.send(embed=embeds.erro("Não consegui entrar no canal de voz."))
        elif t.vc.channel != voz.channel:
            await t.vc.move_to(voz.channel)

        t.canal_texto = interaction.channel
        t.parando = False
        espaco = LIMITE_FILA - len(t.fila)
        t.fila.extend(faixas[:espaco])

        if len(faixas) == 1:
            f = faixas[0]
            if t.tocando:
                e = discord.Embed(title="➕ Adicionada à fila", description=f"**[{f.titulo}]({f.pagina})**", color=COR)
                e.add_field(name="Posição", value=str(len(t.fila)))
                e.add_field(name="Duração", value=formatar_duracao(f.duracao))
                if f.thumb:
                    e.set_thumbnail(url=f.thumb)
            else:
                e = discord.Embed(description=f"🔎 Encontrei **{f.titulo}** ({f.fonte}). Preparando...", color=COR)
        else:
            e = discord.Embed(title="📃 Playlist adicionada",
                              description=f"**{min(len(faixas), espaco)}** músicas foram para a fila.", color=COR)
        await interaction.followup.send(embed=e)

        if not t.tocando:
            await t.tocar_proxima()

    @app_commands.command(name="pular", description="Pula para a próxima música.")
    @app_commands.guild_only()
    async def pular(self, interaction: discord.Interaction):
        t = await self._no_mesmo_canal(interaction)
        if t:
            titulo = t.atual.titulo
            t.pular()
            await interaction.response.send_message(embed=embeds.sucesso(f"Pulei **{titulo}**."))

    @app_commands.command(name="parar", description="Para a música, limpa a fila e sai do canal.")
    @app_commands.guild_only()
    async def parar(self, interaction: discord.Interaction):
        t = await self._no_mesmo_canal(interaction, precisa_tocar=False)
        if t:
            await t.parar()
            await interaction.response.send_message(embed=embeds.sucesso("Parei a música e saí do canal. Até mais! 👋"))

    @app_commands.command(name="pausar", description="Pausa a música.")
    @app_commands.guild_only()
    async def pausar(self, interaction: discord.Interaction):
        t = await self._no_mesmo_canal(interaction)
        if not t:
            return
        if t.vc.is_paused():
            return await self._erro(interaction, "Já está pausada. Use /continuar.")
        t.vc.pause()
        t.pausado_em = time.monotonic()
        await interaction.response.send_message(embed=embeds.sucesso("⏸️ Música pausada."))

    @app_commands.command(name="continuar", description="Continua a música pausada.")
    @app_commands.guild_only()
    async def continuar(self, interaction: discord.Interaction):
        t = await self._no_mesmo_canal(interaction)
        if not t:
            return
        if not t.vc.is_paused():
            return await self._erro(interaction, "A música não está pausada.")
        if t.pausado_em:
            t.inicio += time.monotonic() - t.pausado_em
            t.pausado_em = None
        t.vc.resume()
        await interaction.response.send_message(embed=embeds.sucesso("▶️ Música continuando."))

    @app_commands.command(name="tocando", description="Mostra a música que está tocando agora.")
    @app_commands.guild_only()
    async def tocando(self, interaction: discord.Interaction):
        t = self.tocador(interaction.guild)
        if not t.atual:
            return await self._erro(interaction, "Não estou tocando nada agora.")
        e = t.embed_tocando("⏸️ Pausada" if t.vc and t.vc.is_paused() else "🎶 Tocando agora")
        if t.atual.duracao:
            feito = min(t.tempo_atual(), t.atual.duracao)
            pos = int(14 * feito / t.atual.duracao)
            barra = "▬" * pos + "🔘" + "▬" * (14 - pos)
            e.add_field(name="Progresso",
                        value=f"`{formatar_duracao(feito)}` {barra} `{formatar_duracao(t.atual.duracao)}`",
                        inline=False)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="fila", description="Mostra as próximas músicas.")
    @app_commands.describe(pagina="Página da fila")
    @app_commands.guild_only()
    async def fila(self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 100] = 1):
        t = self.tocador(interaction.guild)
        if not t.atual and not t.fila:
            return await self._erro(interaction, "A fila está vazia. Use /tocar!")
        por_pagina = 10
        total_paginas = max(1, -(-len(t.fila) // por_pagina))
        pagina = min(pagina, total_paginas)
        ini = (pagina - 1) * por_pagina
        linhas = [f"`{i + 1}.` [{f.titulo[:60]}]({f.pagina}) · {formatar_duracao(f.duracao)}"
                  for i, f in enumerate(t.fila[ini:ini + por_pagina], start=ini)]
        e = discord.Embed(title="📃 Fila de músicas", color=COR)
        if t.atual:
            e.add_field(name="Tocando agora", value=f"[{t.atual.titulo}]({t.atual.pagina})", inline=False)
        e.add_field(name=f"Próximas ({len(t.fila)})", value="\n".join(linhas) or "Nada depois desta.", inline=False)
        total = sum(f.duracao or 0 for f in t.fila)
        e.set_footer(text=f"Página {pagina}/{total_paginas} · {formatar_duracao(total)} no total · loop: {LOOPS[t.loop]}")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="volume", description="Muda o volume (0 a 150).")
    @app_commands.describe(nivel="Volume em porcentagem")
    @app_commands.guild_only()
    async def volume(self, interaction: discord.Interaction, nivel: app_commands.Range[int, 0, 150]):
        t = await self._no_mesmo_canal(interaction)
        if not t:
            return
        t.volume = nivel / 100
        if t.vc and isinstance(t.vc.source, discord.PCMVolumeTransformer):
            t.vc.source.volume = t.volume
        await interaction.response.send_message(embed=embeds.sucesso(f"🔊 Volume em **{nivel}%**."))

    @app_commands.command(name="loop", description="Repete a música atual ou a fila inteira.")
    @app_commands.describe(modo="Como repetir")
    @app_commands.choices(modo=[Choice(name=nome, value=chave) for chave, nome in LOOPS.items()])
    @app_commands.guild_only()
    async def loop(self, interaction: discord.Interaction, modo: Choice[str]):
        t = await self._no_mesmo_canal(interaction)
        if t:
            t.loop = modo.value
            await interaction.response.send_message(embed=embeds.sucesso(f"Loop: **{LOOPS[t.loop]}**."))

    @app_commands.command(name="embaralhar", description="Embaralha a fila.")
    @app_commands.guild_only()
    async def embaralhar(self, interaction: discord.Interaction):
        t = await self._no_mesmo_canal(interaction)
        if not t:
            return
        if len(t.fila) < 2:
            return await self._erro(interaction, "Precisa de pelo menos 2 músicas na fila.")
        random.shuffle(t.fila)
        await interaction.response.send_message(embed=embeds.sucesso(f"🔀 Embaralhei {len(t.fila)} músicas."))

    @app_commands.command(name="remover", description="Tira uma música da fila pela posição.")
    @app_commands.describe(posicao="Posição na /fila")
    @app_commands.guild_only()
    async def remover(self, interaction: discord.Interaction, posicao: app_commands.Range[int, 1, LIMITE_FILA]):
        t = await self._no_mesmo_canal(interaction, precisa_tocar=False)
        if not t:
            return
        if posicao > len(t.fila):
            return await self._erro(interaction, f"A fila só tem {len(t.fila)} músicas.")
        faixa = t.fila.pop(posicao - 1)
        await interaction.response.send_message(embed=embeds.sucesso(f"Tirei **{faixa.titulo}** da fila."))

    # ----- sair quando ficar sozinho -----

    @commands.Cog.listener()
    async def on_voice_state_update(self, membro: discord.Member, antes: discord.VoiceState,
                                    depois: discord.VoiceState):
        t = self.tocadores.get(membro.guild.id)
        if not t or not t.vc:
            return
        if membro.id == self.bot.user.id and depois.channel is None:
            # Fui desconectado (ou alguém me tirou do canal)
            t.fila.clear()
            t.atual = None
            t.cancelar_saida()
            return
        pessoas = [m for m in t.vc.channel.members if not m.bot]
        if not pessoas:
            t.agendar_saida(SAIR_SOZINHO, "porque fiquei sozinho")
        elif t.atual:
            t.cancelar_saida()


async def setup(bot):
    await bot.add_cog(Musica(bot))
