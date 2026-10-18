"""Xadrez no Discord: contra alguém ou contra o bot, com tabuleiro desenhado em imagem."""
import asyncio
import concurrent.futures
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import chess
import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds, moeda
from utils.xadrez import NOME_PECA, NIVEIS, SIMBOLO, bot_aceita_empate, desenhar, ler_lance, lance_em_portugues, melhor_lance
from utils.mensagens import mensagem_duravel
from cogs.conquistas import registrar_depois

# O bot pensa num processo separado: assim, enquanto ele calcula, o resto do Harle Bot continua respondendo.
_PENSADOR = concurrent.futures.ProcessPoolExecutor(max_workers=1)


def _pensar(fen: str, nivel: str) -> str:
    """Roda no processo separado (recebe e devolve texto para ser rápido de transferir)."""
    return melhor_lance(chess.Board(fen), nivel, limite_segundos=4.0).uci()


TEMPO_PARA_JOGAR = 300   # 5 minutos sem jogar = derrota
COR = 0x779556
NOME_NIVEL = {"facil": "Fácil", "medio": "Médio", "dificil": "Difícil"}


@dataclass
class Jogador:
    id: int
    nome: str
    bot: bool = False

    @property
    def mencao(self) -> str:
        return f"**{self.nome}**" if self.bot else f"<@{self.id}>"


class PartidaXadrez:
    def __init__(self, cog: "XadrezCog", guild_id: int, brancas: Jogador, pretas: Jogador, aposta: int,
                 nivel: str = "medio"):
        self.cog, self.bot = cog, cog.bot
        self.guild_id = guild_id
        self.brancas, self.pretas = brancas, pretas
        self.aposta = aposta
        self.nivel = nivel
        self.tabuleiro = chess.Board()
        self.ultimo_lance: Optional[str] = None
        self.empate_proposto_por: Optional[chess.Color] = None
        self.trava = asyncio.Lock()
        self.mensagem: Optional[discord.Message] = None
        self.view = TabuleiroView(self)
        self.ultima_acao = time.monotonic()
        self.encerrada = False
        self.resultado: Optional[str] = None
        self._vigia: Optional[asyncio.Task] = None

    # ----- consultas -----

    def jogador(self, cor: chess.Color) -> Jogador:
        return self.brancas if cor == chess.WHITE else self.pretas

    @property
    def da_vez(self) -> Jogador:
        return self.jogador(self.tabuleiro.turn)

    def cor_de(self, user_id: int) -> Optional[chess.Color]:
        if not self.brancas.bot and self.brancas.id == user_id:
            return chess.WHITE
        if not self.pretas.bot and self.pretas.id == user_id:
            return chess.BLACK
        return None

    @property
    def contra_bot(self) -> bool:
        return self.brancas.bot or self.pretas.bot

    def perspectiva(self) -> chess.Color:
        if self.contra_bot:
            return chess.BLACK if self.brancas.bot else chess.WHITE
        return self.tabuleiro.turn

    # ----- visual -----

    def embed(self) -> discord.Embed:
        t = self.tabuleiro
        e = discord.Embed(title="♟️ Xadrez", color=COR)
        e.description = f"⬜ {self.brancas.mencao}  vs  ⬛ {self.pretas.mencao}"
        if self.contra_bot:
            e.description += f"\nBot no nível **{NOME_NIVEL[self.nivel]}**"
        if self.ultimo_lance:
            numero = (len(t.move_stack) + 1) // 2
            e.add_field(name="Último lance", value=f"{numero}. {self.ultimo_lance}")
        if self.resultado:
            e.add_field(name="Resultado", value=self.resultado, inline=False)
        else:
            vez = f"{'⬜ Brancas' if t.turn == chess.WHITE else '⬛ Pretas'} ({self.da_vez.mencao})"
            if t.is_check():
                vez += "\n⚠️ **Xeque!**"
            e.add_field(name="Vez", value=vez)
            if self.empate_proposto_por is not None:
                quem = self.jogador(self.empate_proposto_por).mencao
                e.add_field(name="🤝 Empate proposto", value=f"{quem} propôs empate.", inline=False)
            e.set_footer(text="Escolha a peça e a casa nos menus, ou digite o lance (ex.: e4, Cf3, O-O). "
                              "5 minutos sem jogar = derrota.")
        if self.aposta:
            e.add_field(name="Em jogo", value=moeda.fmt(self.aposta * 2))
        e.set_image(url="attachment://tabuleiro.png")
        return e

    async def payload(self) -> Dict:
        # desenha primeiro e só depois troca os botões, para não deixar botões "soltos" enquanto desenha
        imagem = await asyncio.to_thread(desenhar, self.tabuleiro.copy(), self.perspectiva())
        if not self.encerrada:
            self.view.montar()
        arquivo = discord.File(imagem, filename="tabuleiro.png")
        return {"content": None, "embed": self.embed(), "attachments": [arquivo],
                "view": None if self.encerrada else self.view}

    async def atualizar(self):
        if self.mensagem:
            try:
                await self.mensagem.edit(**(await self.payload()))
            except discord.HTTPException:
                pass

    # ----- fluxo -----

    async def comecar(self, interaction: discord.Interaction, nova_mensagem: bool):
        dados = await self.payload()
        if nova_mensagem:
            arquivo = dados.pop("attachments")[0]
            dados.pop("content")
            await interaction.response.send_message(file=arquivo, **dados)
            self.mensagem = await mensagem_duravel(interaction)
        else:
            await interaction.response.edit_message(**dados)
            self.mensagem = interaction.message
        self._vigia = asyncio.create_task(self._vigiar())
        self.agendar_bot()

    def agendar_bot(self):
        if not self.encerrada and self.da_vez.bot and not self.tabuleiro.is_game_over():
            asyncio.create_task(self._vez_do_bot())

    async def _vez_do_bot(self):
        await asyncio.sleep(0.6)
        if self.encerrada or not self.da_vez.bot:
            return
        fen = self.tabuleiro.fen()
        try:
            uci = await asyncio.get_running_loop().run_in_executor(_PENSADOR, _pensar, fen, self.nivel)
        except Exception:
            uci = (await asyncio.to_thread(melhor_lance, chess.Board(fen), "facil")).uci()
        async with self.trava:   # só trava para aplicar o lance, não enquanto pensa
            if self.encerrada or not self.da_vez.bot or self.tabuleiro.fen() != fen:
                return
            self._aplicar(chess.Move.from_uci(uci))
        await self._depois_do_lance()

    def _aplicar(self, lance: chess.Move):
        self.ultimo_lance = lance_em_portugues(self.tabuleiro, lance)
        self.tabuleiro.push(lance)
        self.empate_proposto_por = None
        self.view.casa_escolhida = None
        self.ultima_acao = time.monotonic()

    async def jogar_humano(self, interaction: discord.Interaction, lance: chess.Move):
        async with self.trava:
            if self.encerrada:
                return await interaction.response.defer()
            if self.cor_de(interaction.user.id) != self.tabuleiro.turn:
                return await interaction.response.send_message("Não é a sua vez.", ephemeral=True)
            if lance not in self.tabuleiro.legal_moves:
                return await interaction.response.send_message("Esse lance não é permitido.", ephemeral=True)
            self._aplicar(lance)
            fim = self._verificar_fim()
            if fim:
                await self._finalizar(*fim)
                return await interaction.response.edit_message(**(await self.payload()))
            await interaction.response.edit_message(**(await self.payload()))
        self.agendar_bot()

    async def _depois_do_lance(self):
        fim = self._verificar_fim()
        if fim:
            await self._finalizar(*fim)
        await self.atualizar()
        self.agendar_bot()

    def _verificar_fim(self):
        desfecho = self.tabuleiro.outcome(claim_draw=True)
        if desfecho is None:
            return None
        motivos = {
            chess.Termination.CHECKMATE: "Xeque-mate!",
            chess.Termination.STALEMATE: "Afogamento (empate).",
            chess.Termination.INSUFFICIENT_MATERIAL: "Material insuficiente (empate).",
            chess.Termination.THREEFOLD_REPETITION: "Repetição de posição (empate).",
            chess.Termination.FIVEFOLD_REPETITION: "Repetição de posição (empate).",
            chess.Termination.FIFTY_MOVES: "Regra dos 50 lances (empate).",
            chess.Termination.SEVENTYFIVE_MOVES: "Regra dos 75 lances (empate).",
        }
        return desfecho.winner, motivos.get(desfecho.termination, "Fim de jogo.")

    async def _finalizar(self, vencedor: Optional[chess.Color], motivo: str):
        if self.encerrada:
            return
        self.encerrada = True
        self.view.stop()
        if self._vigia and self._vigia is not asyncio.current_task():
            self._vigia.cancel()
        self.cog.liberar(self)
        if vencedor is None:
            self.resultado = f"🤝 {motivo}"
            for j in (self.brancas, self.pretas):
                if self.aposta and not j.bot:
                    await self.bot.db.add_coins(self.guild_id, j.id, self.aposta)
            if self.aposta:
                self.resultado += " As apostas foram devolvidas."
        else:
            ganhador = self.jogador(vencedor)
            if not ganhador.bot:
                canal = getattr(self.mensagem, "channel", None)
                registrar_depois(self.bot, self.guild_id, ganhador.id, "xadrez_vitorias", canal=canal)
                if self.contra_bot and self.nivel == "dificil":
                    registrar_depois(self.bot, self.guild_id, ganhador.id, "xadrez_bot_dificil", canal=canal)
            self.resultado = f"🏆 {motivo} {ganhador.mencao} venceu com as {'brancas' if vencedor else 'pretas'}!"
            if self.aposta and not ganhador.bot:
                await self.bot.db.add_coins(self.guild_id, ganhador.id, self.aposta * 2)
                self.resultado += f" Levou {moeda.fmt(self.aposta * 2)}."

    async def desistir(self, interaction: discord.Interaction, cor: chess.Color):
        async with self.trava:
            if self.encerrada:
                return await interaction.response.defer()
            await self._finalizar(not cor, f"{self.jogador(cor).nome} desistiu.")
            await interaction.response.edit_message(**(await self.payload()))

    async def _vigiar(self):
        while not self.encerrada:
            await asyncio.sleep(15)
            if self.encerrada:
                return
            if self.da_vez.bot or time.monotonic() - self.ultima_acao < TEMPO_PARA_JOGAR:
                continue
            async with self.trava:
                cor = self.tabuleiro.turn
                await self._finalizar(not cor, f"⏰ {self.jogador(cor).nome} demorou demais.")
            await self.atualizar()
            return


# ================================ VIEWS ================================

class TabuleiroView(discord.ui.View):
    def __init__(self, partida: PartidaXadrez):
        super().__init__(timeout=None)
        self.partida = partida
        self.casa_escolhida: Optional[int] = None

    def montar(self):
        self.clear_items()
        p, t = self.partida, self.partida.tabuleiro
        vez_humana = not p.da_vez.bot

        # menu 1: peças que podem se mover
        casas = sorted({l.from_square for l in t.legal_moves}, key=lambda c: (t.piece_type_at(c), c), reverse=True)
        opcoes = []
        for casa in casas[:25]:
            peca = t.piece_at(casa)
            # (as peças de xadrez em Unicode não são emojis válidos no Discord, então vão no texto)
            opcoes.append(discord.SelectOption(
                label=f"{SIMBOLO[peca.piece_type]} {NOME_PECA[peca.piece_type]} {chess.square_name(casa)}",
                value=str(casa), default=casa == self.casa_escolhida))
        if not opcoes:
            opcoes = [discord.SelectOption(label="—", value="-1")]
        menu_peca = discord.ui.Select(placeholder="1. Escolha a peça", options=opcoes, row=0,
                                      disabled=not vez_humana or not casas)
        menu_peca.callback = self.escolher_peca
        self.add_item(menu_peca)

        # menu 2: para onde ela vai
        destinos = []
        if self.casa_escolhida is not None:
            lances = [l for l in t.legal_moves if l.from_square == self.casa_escolhida]
            lances.sort(key=lambda l: (not t.is_capture(l), l.to_square))
            for lance in lances[:25]:
                texto = lance_em_portugues(t, lance)
                rotulo = chess.square_name(lance.to_square)
                if t.is_castling(lance):
                    rotulo = "Roque " + ("pequeno" if chess.square_file(lance.to_square) == 6 else "grande")
                elif lance.promotion:
                    rotulo += f" = {NOME_PECA[lance.promotion]}"
                if t.is_capture(lance):
                    rotulo += " (captura)"
                destinos.append(discord.SelectOption(label=rotulo, value=lance.uci(), description=texto))
        menu_destino = discord.ui.Select(placeholder="2. Escolha a casa" if destinos else "2. Escolha uma peça primeiro",
                                         options=destinos or [discord.SelectOption(label="—", value="-")],
                                         disabled=not destinos or not vez_humana, row=1)
        menu_destino.callback = self.escolher_destino
        self.add_item(menu_destino)

        self._botao("Digitar lance", "⌨️", discord.ButtonStyle.primary, self.digitar, 2, not vez_humana)
        if p.empate_proposto_por is not None:
            self._botao("Aceitar empate", "🤝", discord.ButtonStyle.success, self.aceitar_empate, 2)
            self._botao("Recusar", "✖️", discord.ButtonStyle.secondary, self.recusar_empate, 2)
        else:
            self._botao("Propor empate", "🤝", discord.ButtonStyle.secondary, self.propor_empate, 2)
        self._botao("Desistir", "🏳️", discord.ButtonStyle.danger, self.desistir, 2)

    def _botao(self, label, emoji, estilo, callback, linha, desativado=False):
        b = discord.ui.Button(label=label, emoji=emoji, style=estilo, row=linha, disabled=desativado)
        b.callback = callback
        self.add_item(b)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.partida.cor_de(interaction.user.id) is None:
            await interaction.response.send_message("Você não está nessa partida. Comece a sua com /xadrez!",
                                                    ephemeral=True)
            return False
        return True

    def _minha_vez(self, interaction: discord.Interaction) -> bool:
        return self.partida.cor_de(interaction.user.id) == self.partida.tabuleiro.turn

    async def escolher_peca(self, interaction: discord.Interaction):
        if not self._minha_vez(interaction):
            return await interaction.response.send_message("Espere a sua vez.", ephemeral=True)
        valor = int(interaction.data["values"][0])
        self.casa_escolhida = valor if valor >= 0 else None
        self.montar()
        await interaction.response.edit_message(view=self)

    async def escolher_destino(self, interaction: discord.Interaction):
        valor = interaction.data["values"][0]
        if valor == "-":
            return await interaction.response.defer()
        await self.partida.jogar_humano(interaction, chess.Move.from_uci(valor))

    async def digitar(self, interaction: discord.Interaction):
        if not self._minha_vez(interaction):
            return await interaction.response.send_message("Espere a sua vez.", ephemeral=True)
        await interaction.response.send_modal(ModalLance(self.partida))

    async def propor_empate(self, interaction: discord.Interaction):
        p = self.partida
        cor = p.cor_de(interaction.user.id)
        if p.contra_bot:
            cor_bot = chess.WHITE if p.brancas.bot else chess.BLACK
            if bot_aceita_empate(p.tabuleiro, cor_bot):
                async with p.trava:
                    await p._finalizar(None, "Empate combinado.")
                    return await interaction.response.edit_message(**(await p.payload()))
            return await interaction.response.send_message("🤖 O bot recusou o empate. Ele acha que está bem!",
                                                           ephemeral=True)
        p.empate_proposto_por = cor
        self.montar()
        await interaction.response.edit_message(embed=p.embed(), view=self)

    async def aceitar_empate(self, interaction: discord.Interaction):
        p = self.partida
        if p.cor_de(interaction.user.id) == p.empate_proposto_por:
            return await interaction.response.send_message("Quem aceita é o outro jogador.", ephemeral=True)
        async with p.trava:
            await p._finalizar(None, "Empate combinado.")
            await interaction.response.edit_message(**(await p.payload()))

    async def recusar_empate(self, interaction: discord.Interaction):
        p = self.partida
        p.empate_proposto_por = None  # o outro recusa, ou quem propôs retira a proposta
        self.montar()
        await interaction.response.edit_message(embed=p.embed(), view=self)

    async def desistir(self, interaction: discord.Interaction):
        await self.partida.desistir(interaction, self.partida.cor_de(interaction.user.id))


class ModalLance(discord.ui.Modal, title="Digite o seu lance"):
    lance = discord.ui.TextInput(label="Lance", placeholder="Ex.: e4, Cf3, Bxc6, O-O, e8=D ou e2e4", max_length=10)

    def __init__(self, partida: PartidaXadrez):
        super().__init__()
        self.partida = partida

    async def on_submit(self, interaction: discord.Interaction):
        lance = ler_lance(self.partida.tabuleiro, str(self.lance))
        if lance is None:
            return await interaction.response.send_message(
                f"Não entendi **{self.lance}** ou esse lance não é permitido agora. "
                "Use letras em português (C cavalo, B bispo, T torre, D dama, R rei) ou do tipo e2e4.",
                ephemeral=True)
        await self.partida.jogar_humano(interaction, lance)


class ConviteXadrez(discord.ui.View):
    def __init__(self, cog: "XadrezCog", guild_id: int, desafiante: discord.Member, desafiado: discord.Member,
                 cor_desafiante: chess.Color, aposta: int):
        super().__init__(timeout=60)
        self.cog, self.guild_id = cog, guild_id
        self.desafiante, self.desafiado = desafiante, desafiado
        self.cor_desafiante, self.aposta = cor_desafiante, aposta
        self.mensagem: Optional[discord.Message] = None
        self.respondido = False

    def texto(self) -> str:
        valendo = f" valendo {moeda.fmt(self.aposta)} de cada um" if self.aposta else ""
        cor = "brancas" if self.cor_desafiante == chess.WHITE else "pretas"
        return (f"♟️ {self.desafiado.mention}, {self.desafiante.mention} te desafiou para uma partida de "
                f"**xadrez**{valendo}! ({self.desafiante.display_name} joga de {cor})")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.desafiado.id:
            return True
        await interaction.response.send_message("Esse convite não é para você.", ephemeral=True)
        return False

    @discord.ui.button(label="Aceitar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceitar(self, interaction: discord.Interaction, _):
        if self.cog.ocupado(self.desafiado.id):
            return await interaction.response.send_message("Você já está numa partida de xadrez.", ephemeral=True)
        if self.aposta and not await self.cog.bot.db.spend_coins(self.guild_id, self.desafiado.id, self.aposta):
            return await interaction.response.send_message(f"Você precisa de {moeda.fmt(self.aposta)}.",
                                                           ephemeral=True)
        self.respondido = True
        self.stop()
        a = Jogador(self.desafiante.id, self.desafiante.display_name)
        b = Jogador(self.desafiado.id, self.desafiado.display_name)
        brancas, pretas = (a, b) if self.cor_desafiante == chess.WHITE else (b, a)
        partida = self.cog.criar(self.guild_id, brancas, pretas, self.aposta)
        await partida.comecar(interaction, nova_mensagem=False)

    @discord.ui.button(label="Recusar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def recusar(self, interaction: discord.Interaction, _):
        self.respondido = True
        self.stop()
        await self.cog.devolver(self.guild_id, self.desafiante.id, self.aposta)
        await interaction.response.edit_message(content=f"{self.desafiado.mention} recusou o xadrez.", view=None)

    async def on_timeout(self):
        if self.respondido:
            return
        await self.cog.devolver(self.guild_id, self.desafiante.id, self.aposta)
        if self.mensagem:
            try:
                await self.mensagem.edit(content="⏰ O convite de xadrez expirou.", view=None)
            except discord.HTTPException:
                pass


# ================================ COG ================================

class XadrezCog(commands.Cog, name="Xadrez"):
    def __init__(self, bot):
        self.bot = bot
        self.partidas: List[PartidaXadrez] = []

    def ocupado(self, user_id: int) -> bool:
        return any(p.cor_de(user_id) is not None and not p.encerrada for p in self.partidas)

    def criar(self, guild_id, brancas, pretas, aposta, nivel="medio") -> PartidaXadrez:
        partida = PartidaXadrez(self, guild_id, brancas, pretas, aposta, nivel)
        self.partidas.append(partida)
        return partida

    def liberar(self, partida: PartidaXadrez):
        if partida in self.partidas:
            self.partidas.remove(partida)

    async def devolver(self, guild_id: int, user_id: int, aposta: int):
        if aposta:
            await self.bot.db.add_coins(guild_id, user_id, aposta)

    @app_commands.command(name="xadrez", description="Xadrez contra alguém ou contra o bot, com tabuleiro em imagem.")
    @app_commands.describe(oponente="Quem desafiar (vazio = contra o bot)", cor="Com que cor você joga",
                           dificuldade="Nível do bot (só contra o bot)", aposta=f"Aposta em {moeda.NOME} (opcional)")
    @app_commands.choices(
        cor=[Choice(name="Brancas", value="brancas"), Choice(name="Pretas", value="pretas"),
             Choice(name="Aleatório", value="aleatorio")],
        dificuldade=[Choice(name=NOME_NIVEL[n], value=n) for n in NIVEIS],
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    async def xadrez(self, interaction: discord.Interaction, oponente: Optional[discord.Member] = None,
                     cor: Optional[Choice[str]] = None, dificuldade: Optional[Choice[str]] = None,
                     aposta: Optional[app_commands.Range[int, 1, moeda.APOSTA_MAXIMA]] = None):
        eu = interaction.user
        aposta = aposta or 0
        if self.ocupado(eu.id):
            return await interaction.response.send_message(embed=embeds.erro("Você já está numa partida de xadrez."),
                                                           ephemeral=True)
        contra_bot = oponente is None or oponente.id == self.bot.user.id
        if not contra_bot and (oponente.bot or oponente.id == eu.id):
            return await interaction.response.send_message(
                embed=embeds.erro("Escolha outra pessoa, ou deixe vazio para jogar contra mim."), ephemeral=True)
        escolha = cor.value if cor else "aleatorio"
        minha_cor = chess.WHITE if escolha == "brancas" else chess.BLACK if escolha == "pretas" \
            else random.choice([chess.WHITE, chess.BLACK])
        if aposta and not await self.bot.db.spend_coins(interaction.guild.id, eu.id, aposta):
            return await interaction.response.send_message(embed=embeds.erro(f"Você não tem {moeda.fmt(aposta)}."),
                                                           ephemeral=True)

        if contra_bot:
            humano = Jogador(eu.id, eu.display_name)
            robo = Jogador(-1, "Harle Bot", bot=True)
            brancas, pretas = (humano, robo) if minha_cor == chess.WHITE else (robo, humano)
            nivel = dificuldade.value if dificuldade else "medio"
            partida = self.criar(interaction.guild.id, brancas, pretas, aposta, nivel)
            await partida.comecar(interaction, nova_mensagem=True)
            return

        convite = ConviteXadrez(self, interaction.guild.id, eu, oponente, minha_cor, aposta)
        await interaction.response.send_message(convite.texto(), view=convite,
                                                allowed_mentions=discord.AllowedMentions(users=[oponente]))
        convite.mensagem = await mensagem_duravel(interaction)


async def setup(bot):
    await bot.add_cog(XadrezCog(bot))
