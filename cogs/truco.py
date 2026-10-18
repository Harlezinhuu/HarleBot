"""Truco Paulista no Discord: 1x1, 2x2 (com bots completando a mesa) e contra o bot."""
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds, moeda, truco_ia
from utils.truco import EMPATE, NOME_PEDIDO, Carta, JogadaInvalida, Truco

TEMPO_PARA_AGIR = 120     # segundos; quem demorar mais que isso perde a partida
PAUSA_DO_BOT = 1.3        # segundos entre as jogadas dos bots, para dar para acompanhar
NOMES_BOTS = ["Harle Bot", "Bot Zé", "Bot Tião"]
COR = 0x1B7F3B            # verde de mesa de baralho
ICONE_TIME = ["🔵", "🔴"]


@dataclass
class Jogador:
    id: int
    nome: str
    bot: bool = False

    @property
    def mencao(self) -> str:
        return f"**{self.nome}**" if self.bot else f"<@{self.id}>"


# ================================ PARTIDA ================================

class Partida:
    def __init__(self, cog: "TrucoCog", guild_id: int, jogadores: List[Jogador], aposta: int):
        self.cog = cog
        self.bot = cog.bot
        self.guild_id = guild_id
        self.jogadores = jogadores
        self.aposta = aposta
        self.jogo = Truco(len(jogadores))
        self.jogo.nomes = [j.nome for j in jogadores]
        self.jogo.log.clear()
        self.trava = asyncio.Lock()
        self.mensagem: Optional[discord.Message] = None
        self.view = MesaView(self)
        self.ultima_acao = time.monotonic()
        self._bots_rodando = False
        self._vigia: Optional[asyncio.Task] = None
        self.encerrada = False

    # ----- consultas -----

    @property
    def humanos(self) -> List[Jogador]:
        return [j for j in self.jogadores if not j.bot]

    def idx_de(self, user_id: int) -> Optional[int]:
        return next((i for i, j in enumerate(self.jogadores) if j.id == user_id and not j.bot), None)

    def membros_do_time(self, time_: int) -> List[int]:
        return [i for i in range(len(self.jogadores)) if i % 2 == time_]

    def time_tem_humano(self, time_: int) -> bool:
        return any(not self.jogadores[i].bot for i in self.membros_do_time(time_))

    def nome_time(self, time_: int) -> str:
        return f"{ICONE_TIME[time_]} " + " e ".join(self.jogadores[i].nome for i in self.membros_do_time(time_))

    # ----- visual -----

    def embed(self) -> discord.Embed:
        j = self.jogo
        modo = "1x1" if len(self.jogadores) == 2 else "2x2"
        e = discord.Embed(title=f"🃏 Truco Paulista · {modo}", color=COR)
        e.description = (f"{self.nome_time(0)} **{j.pontos[0]}**  ×  **{j.pontos[1]}** {self.nome_time(1)}\n"
                         f"Partida até 12 pontos")

        if not j.acabou:
            e.add_field(name="Vira", value=f"`{j.vira}` → manilha **{j.manilha}**")
            valendo = f"**{j.valor}** {'ponto' if j.valor == 1 else 'pontos'}"
            if j.pedido:
                valendo += f"\n🗣️ {NOME_PEDIDO[j.pedido['valor']]} pedido!"
            e.add_field(name="Mão valendo", value=valendo)
            rodadas = []
            for n, r in enumerate(j.rodadas, start=1):
                rodadas.append(f"{n}ª: {'➖ empate' if r == EMPATE else ICONE_TIME[r]}")
            e.add_field(name="Rodadas", value=" · ".join(rodadas) or "nenhuma ainda")

            mesa = j.mesa or []
            if mesa:
                texto_mesa = "\n".join(f"{self.jogadores[i].nome}: `{c}`" for i, c in mesa)
            elif j.ultima_mesa and j.rodadas:
                texto_mesa = "Última rodada:\n" + "\n".join(f"{self.jogadores[i].nome}: `{c}`" for i, c in j.ultima_mesa)
            else:
                texto_mesa = "Ninguém jogou ainda."
            e.add_field(name="Mesa", value=texto_mesa, inline=False)

        e.add_field(name="Últimas jogadas", value="\n".join(j.log[-5:]) or "A partida começou!", inline=False)
        if self.aposta:
            e.add_field(name="Em jogo", value=moeda.fmt(self.aposta * len(self.jogadores)), inline=False)
        if not j.acabou:
            e.set_footer(text="Use 🃏 Minhas cartas para ver sua mão e jogar. "
                              f"Quem demorar mais de {TEMPO_PARA_AGIR // 60} minutos na vez perde.")
        return e

    def texto_vez(self) -> str:
        tipo, quem = self.jogo.proxima_acao()
        if tipo == "fim":
            verbo = "venceram" if len(self.membros_do_time(quem)) > 1 else "venceu"
            return f"🏆 **{self.nome_time(quem)} {verbo}!**"
        if tipo == "carta":
            return f"👉 Vez de {self.jogadores[quem].mencao}"
        if tipo == "resposta":
            return f"❓ {self.nome_time(quem)}: aceita, corre ou aumenta?"
        return f"✋ {self.nome_time(quem)}: joga a mão de onze ou corre?"

    async def atualizar(self):
        self.view.montar()
        if self.mensagem:
            try:
                await self.mensagem.edit(content=self.texto_vez(), embed=self.embed(), view=self.view,
                                         allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

    # ----- fluxo -----

    async def comecar(self, interaction: discord.Interaction, ja_respondeu: bool = False):
        self.view.montar()
        if ja_respondeu:
            await interaction.edit_original_response(content=self.texto_vez(), embed=self.embed(), view=self.view)
            self.mensagem = await interaction.original_response()
        else:
            await interaction.response.edit_message(content=self.texto_vez(), embed=self.embed(), view=self.view)
            self.mensagem = interaction.message
        self._vigia = asyncio.create_task(self._vigiar())
        self.agendar_bots()

    def agiu(self):
        self.ultima_acao = time.monotonic()

    def agendar_bots(self):
        if not self._bots_rodando and not self.encerrada:
            asyncio.create_task(self._rodar_bots())

    def _proxima_do_bot(self):
        """Devolve uma função que faz a jogada do bot, ou None se a vez é de um humano."""
        j = self.jogo
        tipo, quem = j.proxima_acao()
        if tipo == "carta" and self.jogadores[quem].bot:
            if truco_ia.quer_pedir(j, quem):
                return lambda: j.pedir(quem)
            return lambda: j.jogar(quem, truco_ia.escolher_carta(j, quem))
        if tipo == "resposta" and not self.time_tem_humano(quem):
            return lambda: j.responder(quem, truco_ia.responder(j, quem))
        if tipo == "onze" and not self.time_tem_humano(quem):
            return lambda: j.decidir_onze(quem, truco_ia.decidir_onze(j, quem))
        return None

    async def _rodar_bots(self):
        self._bots_rodando = True
        try:
            while not self.encerrada:
                async with self.trava:
                    if self.jogo.acabou:
                        break
                    tem_jogada = self._proxima_do_bot() is not None
                if not tem_jogada:
                    break
                await asyncio.sleep(PAUSA_DO_BOT)
                async with self.trava:
                    acao = self._proxima_do_bot()
                    if acao is None:
                        continue
                    acao()
                    self.agiu()
                await self.atualizar()
            if self.jogo.acabou:
                await self.encerrar()
        finally:
            self._bots_rodando = False

    async def depois_de_humano(self):
        """Chamado depois de qualquer jogada de pessoa."""
        self.agiu()
        if self.jogo.acabou:
            await self.encerrar()
        else:
            await self.atualizar()
            self.agendar_bots()

    async def _vigiar(self):
        while not self.encerrada:
            await asyncio.sleep(10)
            if self.encerrada or self.jogo.acabou:
                return
            if time.monotonic() - self.ultima_acao < TEMPO_PARA_AGIR or self._bots_rodando:
                continue
            tipo, quem = self.jogo.proxima_acao()
            time_que_demorou = (quem % 2) if tipo == "carta" else quem
            self.jogo.log.append(f"⏰ {self.nome_time(time_que_demorou)} demorou demais.")
            self.jogo.desistir(time_que_demorou)
            await self.encerrar()
            return

    async def encerrar(self):
        if self.encerrada:
            return
        self.encerrada = True
        self.view.stop()
        if self._vigia and self._vigia is not asyncio.current_task():
            self._vigia.cancel()
        self.cog.liberar(self)

        vencedor = self.jogo.vencedor
        premiados = [self.jogadores[i] for i in self.membros_do_time(vencedor) if not self.jogadores[i].bot]
        texto_premio = ""
        if self.aposta and premiados:
            pote = self.aposta * len(self.jogadores)
            parte = pote // len(premiados)
            for p in premiados:
                await self.bot.db.add_coins(self.guild_id, p.id, parte)
            texto_premio = f"\n💰 {', '.join(p.mencao for p in premiados)} levou {moeda.fmt(parte)}" + \
                           (" cada." if len(premiados) > 1 else ".")
        e = self.embed()
        e.color = embeds.VERDE if premiados else embeds.VERMELHO
        if self.mensagem:
            try:
                await self.mensagem.edit(content=self.texto_vez() + texto_premio, embed=e, view=None,
                                         allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass


# ================================ VIEWS ================================

class MesaView(discord.ui.View):
    """Botões públicos da mesa: ver cartas, responder truco, mão de onze e desistir."""

    def __init__(self, partida: Partida):
        super().__init__(timeout=None)
        self.partida = partida

    def montar(self):
        self.clear_items()
        p, j = self.partida, self.partida.jogo
        self._botao("Minhas cartas", "🃏", discord.ButtonStyle.primary, self.ver_cartas)
        tipo, quem = j.proxima_acao()
        if tipo == "resposta":
            self._botao("Aceitar", "👍", discord.ButtonStyle.success, self._resposta("aceitar"))
            self._botao("Correr", "🏃", discord.ButtonStyle.danger, self._resposta("correr"))
            if j.pedido["valor"] < 12:
                proximo = {3: 6, 6: 9, 9: 12}[j.pedido["valor"]]
                self._botao(f"Pedir {NOME_PEDIDO[proximo]}", "🔥", discord.ButtonStyle.secondary,
                            self._resposta("aumentar"))
        elif tipo == "onze":
            self._botao("Jogar a mão de onze", "✅", discord.ButtonStyle.success, self._onze(True))
            self._botao("Correr", "🏃", discord.ButtonStyle.danger, self._onze(False))
        self._botao("Desistir", "🏳️", discord.ButtonStyle.secondary, self.desistir, linha=1)

    def _botao(self, label, emoji, estilo, callback, linha=0):
        b = discord.ui.Button(label=label, emoji=emoji, style=estilo, row=linha)
        b.callback = callback
        self.add_item(b)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.partida.idx_de(interaction.user.id) is None:
            await interaction.response.send_message("Você não está nessa partida. Comece a sua com /truco!",
                                                    ephemeral=True)
            return False
        return True

    async def ver_cartas(self, interaction: discord.Interaction):
        idx = self.partida.idx_de(interaction.user.id)
        view = MaoView(self.partida, idx)
        await interaction.response.send_message(view.texto(), view=view, ephemeral=True)

    def _resposta(self, acao: str):
        async def callback(interaction: discord.Interaction):
            p = self.partida
            idx = p.idx_de(interaction.user.id)
            async with p.trava:
                tipo, time_ = p.jogo.proxima_acao()
                if tipo != "resposta" or idx % 2 != time_:
                    return await interaction.response.send_message("Quem responde é o outro time.", ephemeral=True)
                try:
                    p.jogo.responder(time_, acao)
                except JogadaInvalida as erro:
                    return await interaction.response.send_message(str(erro), ephemeral=True)
            await interaction.response.defer()
            await p.depois_de_humano()
        return callback

    def _onze(self, jogar: bool):
        async def callback(interaction: discord.Interaction):
            p = self.partida
            idx = p.idx_de(interaction.user.id)
            async with p.trava:
                tipo, time_ = p.jogo.proxima_acao()
                if tipo != "onze" or idx % 2 != time_:
                    return await interaction.response.send_message("Quem decide é o time com 11 pontos.",
                                                                   ephemeral=True)
                p.jogo.decidir_onze(time_, jogar)
            await interaction.response.defer()
            await p.depois_de_humano()
        return callback

    async def desistir(self, interaction: discord.Interaction):
        p = self.partida
        idx = p.idx_de(interaction.user.id)
        async with p.trava:
            if p.jogo.acabou:
                return await interaction.response.defer()
            p.jogo.desistir(idx % 2)
        await interaction.response.defer()
        await p.encerrar()


class BotaoCarta(discord.ui.Button):
    def __init__(self, carta: Carta, manilha: bool, liberado: bool):
        super().__init__(label=f"{carta}{' ⭐' if manilha else ''}",
                         style=discord.ButtonStyle.success if manilha else discord.ButtonStyle.secondary,
                         disabled=not liberado)
        self.carta = carta

    async def callback(self, interaction: discord.Interaction):
        await self.view.jogar(interaction, self.carta)


class MaoView(discord.ui.View):
    """A mão de um jogador, numa mensagem que só ele vê."""

    def __init__(self, partida: Partida, idx: int):
        super().__init__(timeout=600)
        self.partida = partida
        self.idx = idx
        j = partida.jogo
        tipo, quem = j.proxima_acao()
        minha_vez = tipo == "carta" and quem == idx and not j.acabou
        for carta in j.maos[idx]:
            self.add_item(BotaoCarta(carta, j.eh_manilha(carta), minha_vez))
        if not j.acabou and not j.sem_truco and j.valor < 12:
            pedido = NOME_PEDIDO[j.proximo_pedido()]
            botao = discord.ui.Button(label=f"Pedir {pedido}!", emoji="🗣️", style=discord.ButtonStyle.danger,
                                      row=1, disabled=not j.pode_pedir(idx))
            botao.callback = self.pedir
            self.add_item(botao)
        atualizar = discord.ui.Button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        atualizar.callback = self.recarregar
        self.add_item(atualizar)

    def texto(self) -> str:
        p, j = self.partida, self.partida.jogo
        if j.acabou:
            return "A partida acabou."
        linhas = [f"**Suas cartas** · vira `{j.vira}` → manilha **{j.manilha}** (⭐)"]
        tipo, quem = j.proxima_acao()
        if tipo == "carta" and quem == self.idx:
            linhas.append("👉 **É a sua vez!** Clique numa carta para jogar.")
        elif tipo == "onze" and quem == self.idx % 2:
            linhas.append("✋ Mão de onze: decida na mesa se o seu time joga ou corre.")
            if len(p.jogadores) == 4:
                parceiro = (self.idx + 2) % 4
                cartas = " ".join(f"`{c}`" for c in j.maos[parceiro])
                linhas.append(f"Cartas do parceiro ({p.jogadores[parceiro].nome}): {cartas}")
        else:
            linhas.append("⏳ Aguarde a sua vez. Use 🔄 para atualizar.")
        if not j.maos[self.idx]:
            linhas.append("Você já jogou todas as cartas desta mão.")
        return "\n".join(linhas)

    async def _redesenhar(self, interaction: discord.Interaction):
        nova = MaoView(self.partida, self.idx)
        await interaction.response.edit_message(content=nova.texto(), view=nova)

    async def recarregar(self, interaction: discord.Interaction):
        await self._redesenhar(interaction)

    async def jogar(self, interaction: discord.Interaction, carta: Carta):
        p = self.partida
        async with p.trava:
            mao = p.jogo.maos[self.idx]
            if carta not in mao:
                return await self._redesenhar(interaction)
            try:
                p.jogo.jogar(self.idx, mao.index(carta))
            except JogadaInvalida as erro:
                return await interaction.response.send_message(str(erro), ephemeral=True)
        await self._redesenhar(interaction)
        await p.depois_de_humano()

    async def pedir(self, interaction: discord.Interaction):
        p = self.partida
        async with p.trava:
            try:
                p.jogo.pedir(self.idx)
            except JogadaInvalida as erro:
                return await interaction.response.send_message(str(erro), ephemeral=True)
        await self._redesenhar(interaction)
        await p.depois_de_humano()


class ConviteTruco(discord.ui.View):
    def __init__(self, cog: "TrucoCog", guild_id: int, desafiante: discord.Member, desafiado: discord.Member,
                 aposta: int):
        super().__init__(timeout=60)
        self.cog, self.guild_id = cog, guild_id
        self.desafiante, self.desafiado, self.aposta = desafiante, desafiado, aposta
        self.mensagem: Optional[discord.Message] = None
        self.respondido = False

    def texto(self) -> str:
        valendo = f" valendo {moeda.fmt(self.aposta)} de cada um" if self.aposta else ""
        return f"🃏 {self.desafiado.mention}, {self.desafiante.mention} te chamou para um **truco 1x1**{valendo}!"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.desafiado.id:
            return True
        await interaction.response.send_message("Esse convite não é para você.", ephemeral=True)
        return False

    @discord.ui.button(label="Aceitar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceitar(self, interaction: discord.Interaction, _):
        if self.cog.ocupado(self.desafiado.id):
            return await interaction.response.send_message("Você já está numa partida de truco.", ephemeral=True)
        if self.aposta and not await self.cog.bot.db.spend_coins(self.guild_id, self.desafiado.id, self.aposta):
            return await interaction.response.send_message(f"Você precisa de {moeda.fmt(self.aposta)}.",
                                                           ephemeral=True)
        self.respondido = True
        self.stop()
        jogadores = [Jogador(self.desafiante.id, self.desafiante.display_name),
                     Jogador(self.desafiado.id, self.desafiado.display_name)]
        partida = self.cog.criar(self.guild_id, jogadores, self.aposta)
        await partida.comecar(interaction)

    @discord.ui.button(label="Recusar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def recusar(self, interaction: discord.Interaction, _):
        self.respondido = True
        self.stop()
        await self.cog.devolver(self.guild_id, [self.desafiante.id], self.aposta)
        await interaction.response.edit_message(content=f"{self.desafiado.mention} recusou o truco.", view=None)

    async def on_timeout(self):
        if self.respondido:
            return
        await self.cog.devolver(self.guild_id, [self.desafiante.id], self.aposta)
        if self.mensagem:
            try:
                await self.mensagem.edit(content="⏰ O convite de truco expirou.", view=None)
            except discord.HTTPException:
                pass


class LobbyTruco(discord.ui.View):
    """Sala do 2x2: cada um escolhe o time; o dono começa e os lugares vazios viram bots."""

    def __init__(self, cog: "TrucoCog", guild_id: int, dono: discord.Member, aposta: int):
        super().__init__(timeout=180)
        self.cog, self.guild_id, self.dono, self.aposta = cog, guild_id, dono, aposta
        self.lugares: List[Optional[discord.Member]] = [dono, None, None, None]  # 0 e 2: azul; 1 e 3: vermelho
        self.mensagem: Optional[discord.Message] = None
        self.comecou = False

    def embed(self) -> discord.Embed:
        e = discord.Embed(title="🃏 Truco Paulista 2x2 · sala de espera", color=COR)
        for time_ in (0, 1):
            nomes = [self.lugares[i].mention if self.lugares[i] else "*vaga (bot)*" for i in (time_, time_ + 2)]
            e.add_field(name=f"{ICONE_TIME[time_]} Time {'Azul' if time_ == 0 else 'Vermelho'}",
                        value="\n".join(nomes))
        if self.aposta:
            e.add_field(name="Entrada", value=moeda.fmt(self.aposta), inline=False)
        e.set_footer(text=f"{self.dono.display_name} começa quando quiser. Vagas vazias viram bots.")
        return e

    async def _entrar(self, interaction: discord.Interaction, time_: int):
        u = interaction.user
        if u in self.lugares:
            atual = self.lugares.index(u)
            if atual % 2 == time_:
                return await interaction.response.send_message("Você já está nesse time.", ephemeral=True)
            livre = next((i for i in (time_, time_ + 2) if self.lugares[i] is None), None)
            if livre is None:
                return await interaction.response.send_message("Esse time está cheio.", ephemeral=True)
            self.lugares[atual], self.lugares[livre] = None, u
            return await interaction.response.edit_message(embed=self.embed(), view=self)
        if self.cog.ocupado(u.id):
            return await interaction.response.send_message("Você já está numa partida de truco.", ephemeral=True)
        livre = next((i for i in (time_, time_ + 2) if self.lugares[i] is None), None)
        if livre is None:
            return await interaction.response.send_message("Esse time está cheio.", ephemeral=True)
        if self.aposta and not await self.cog.bot.db.spend_coins(self.guild_id, u.id, self.aposta):
            return await interaction.response.send_message(f"Você precisa de {moeda.fmt(self.aposta)} para entrar.",
                                                           ephemeral=True)
        self.lugares[livre] = u
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Time Azul", emoji="🔵", style=discord.ButtonStyle.primary)
    async def azul(self, interaction: discord.Interaction, _):
        await self._entrar(interaction, 0)

    @discord.ui.button(label="Time Vermelho", emoji="🔴", style=discord.ButtonStyle.danger)
    async def vermelho(self, interaction: discord.Interaction, _):
        await self._entrar(interaction, 1)

    @discord.ui.button(label="Sair", emoji="🚪", style=discord.ButtonStyle.secondary)
    async def sair(self, interaction: discord.Interaction, _):
        u = interaction.user
        if u not in self.lugares:
            return await interaction.response.send_message("Você não está na sala.", ephemeral=True)
        if u.id == self.dono.id:
            return await self.cancelar(interaction)
        self.lugares[self.lugares.index(u)] = None
        await self.cog.devolver(self.guild_id, [u.id], self.aposta)
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Começar", emoji="▶️", style=discord.ButtonStyle.success, row=1)
    async def comecar(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.dono.id:
            return await interaction.response.send_message("Só quem criou a sala pode começar.", ephemeral=True)
        self.comecou = True
        self.stop()
        nomes_bots = iter(NOMES_BOTS)
        jogadores = []
        for i, membro in enumerate(self.lugares):
            if membro:
                jogadores.append(Jogador(membro.id, membro.display_name))
            else:
                jogadores.append(Jogador(-(i + 1), next(nomes_bots), bot=True))
        partida = self.cog.criar(self.guild_id, jogadores, self.aposta)
        await partida.comecar(interaction)

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.secondary, row=1)
    async def botao_cancelar(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.dono.id:
            return await interaction.response.send_message("Só quem criou a sala pode cancelar.", ephemeral=True)
        await self.cancelar(interaction)

    async def cancelar(self, interaction: discord.Interaction):
        self.comecou = True
        self.stop()
        await self.cog.devolver(self.guild_id, [m.id for m in self.lugares if m], self.aposta)
        await interaction.response.edit_message(content="Sala de truco cancelada.", embed=None, view=None)

    async def on_timeout(self):
        if self.comecou:
            return
        await self.cog.devolver(self.guild_id, [m.id for m in self.lugares if m], self.aposta)
        if self.mensagem:
            try:
                await self.mensagem.edit(content="⏰ A sala de truco expirou.", embed=None, view=None)
            except discord.HTTPException:
                pass


# ================================ COG ================================

class TrucoCog(commands.Cog, name="Truco"):
    def __init__(self, bot):
        self.bot = bot
        self.partidas: List[Partida] = []

    def ocupado(self, user_id: int) -> bool:
        return any(p.idx_de(user_id) is not None and not p.encerrada for p in self.partidas)

    def criar(self, guild_id: int, jogadores: List[Jogador], aposta: int) -> Partida:
        partida = Partida(self, guild_id, jogadores, aposta)
        self.partidas.append(partida)
        return partida

    def liberar(self, partida: Partida):
        if partida in self.partidas:
            self.partidas.remove(partida)

    async def devolver(self, guild_id: int, ids: List[int], aposta: int):
        if aposta:
            for uid in ids:
                await self.bot.db.add_coins(guild_id, uid, aposta)

    @app_commands.command(name="truco", description="Truco Paulista: 1x1, 2x2 ou contra o bot, com aposta opcional.")
    @app_commands.describe(modo="1 contra 1 ou em duplas",
                           oponente="No 1x1: quem desafiar (vazio = contra o bot)",
                           aposta=f"Entrada de cada jogador em {moeda.NOME} (opcional)")
    @app_commands.choices(modo=[Choice(name="1 contra 1", value="1x1"), Choice(name="2 contra 2 (duplas)", value="2x2")])
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    async def truco(self, interaction: discord.Interaction, modo: Choice[str],
                    oponente: Optional[discord.Member] = None,
                    aposta: Optional[app_commands.Range[int, 1, 10_000_000]] = None):
        aposta = aposta or 0
        eu = interaction.user
        if self.ocupado(eu.id):
            return await interaction.response.send_message(embed=embeds.erro("Você já está numa partida de truco."),
                                                           ephemeral=True)
        if modo.value == "1x1" and oponente and not oponente.bot and oponente.id == eu.id:
            return await interaction.response.send_message(embed=embeds.erro("Jogar contra você mesmo não vale!"),
                                                           ephemeral=True)
        if modo.value == "1x1" and oponente and oponente.bot and oponente.id != self.bot.user.id:
            return await interaction.response.send_message(
                embed=embeds.erro("Esse bot não sabe jogar truco. Deixe o oponente vazio para jogar contra mim!"),
                ephemeral=True)
        if aposta and not await self.bot.db.spend_coins(interaction.guild.id, eu.id, aposta):
            return await interaction.response.send_message(embed=embeds.erro(f"Você não tem {moeda.fmt(aposta)}."),
                                                           ephemeral=True)

        if modo.value == "2x2":
            sala = LobbyTruco(self, interaction.guild.id, eu, aposta)
            await interaction.response.send_message(embed=sala.embed(), view=sala)
            sala.mensagem = await interaction.original_response()
            return

        if oponente is None or oponente.id == self.bot.user.id:
            jogadores = [Jogador(eu.id, eu.display_name), Jogador(-1, NOMES_BOTS[0], bot=True)]
            partida = self.criar(interaction.guild.id, jogadores, aposta)
            await interaction.response.send_message("Embaralhando...")
            await partida.comecar(interaction, ja_respondeu=True)
            return

        convite = ConviteTruco(self, interaction.guild.id, eu, oponente, aposta)
        await interaction.response.send_message(convite.texto(), view=convite,
                                                allowed_mentions=discord.AllowedMentions(users=[oponente]))
        convite.mensagem = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(TrucoCog(bot))
