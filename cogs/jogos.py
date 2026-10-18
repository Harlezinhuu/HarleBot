"""Jogos: quiz, forca, jogo da velha e pedra-papel-tesoura."""
import random
from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from conteudo.palavras import PALAVRAS
from conteudo.perguntas import PERGUNTAS
from utils import embeds, moeda
from utils.jogos import DESENHOS, MAX_ERROS, Forca, jogada_do_bot, resultado_ppt, vencedor_velha
from utils.mensagens import mensagem_duravel

PREMIO_QUIZ = 50
PREMIO_FORCA_LETRA = 80
PREMIO_FORCA_PALAVRA = 120
# dificuldade -> (nome, chance do bot errar de propósito, prêmio por vencer, prêmio por empatar)
DIFICULDADES = {
    "facil": ("Fácil", 0.6, 50, 0),
    "medio": ("Médio", 0.25, 100, 0),
    "impossivel": ("Impossível", 0.0, 0, 60),
}
LETRAS = ["A", "B", "C", "D"]


async def _desativar(view: discord.ui.View, mensagem: Optional[discord.Message]):
    for item in view.children:
        item.disabled = True
    if mensagem:
        try:
            await mensagem.edit(view=view)
        except discord.HTTPException:
            pass


# ================================ QUIZ ================================

class BotaoQuiz(discord.ui.Button):
    def __init__(self, indice: int, texto: str):
        super().__init__(label=f"{LETRAS[indice]}) {texto}"[:80], style=discord.ButtonStyle.secondary)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction):
        await self.view.responder(interaction, self)


class QuizView(discord.ui.View):
    def __init__(self, bot, pergunta: dict):
        super().__init__(timeout=30)
        self.bot = bot
        self.pergunta = pergunta
        self.ja_tentaram = set()
        self.mensagem: Optional[discord.Message] = None
        self.botoes: List[BotaoQuiz] = []
        for i, opcao in enumerate(pergunta["opcoes"]):
            botao = BotaoQuiz(i, opcao)
            self.botoes.append(botao)
            self.add_item(botao)

    def _revelar(self):
        for botao in self.botoes:
            botao.disabled = True
            if botao.indice == self.pergunta["certa"]:
                botao.style = discord.ButtonStyle.success

    async def responder(self, interaction: discord.Interaction, botao: BotaoQuiz):
        if interaction.user.id in self.ja_tentaram:
            return await interaction.response.send_message("Você já respondeu essa! Espere a próxima.", ephemeral=True)
        self.ja_tentaram.add(interaction.user.id)

        if botao.indice != self.pergunta["certa"]:
            return await interaction.response.send_message("❌ Errou! Agora só os outros podem tentar.", ephemeral=True)

        self.stop()
        self._revelar()
        saldo = await self.bot.db.add_coins(interaction.guild.id, interaction.user.id, PREMIO_QUIZ)
        e = interaction.message.embeds[0]
        e.color = embeds.VERDE
        e.add_field(name="🏆 Acertou primeiro", value=f"{interaction.user.mention} ganhou {moeda.fmt(PREMIO_QUIZ)}")
        e.set_footer(text=f"Saldo de {interaction.user.display_name}: {saldo:,}".replace(",", "."))
        await interaction.response.edit_message(embed=e, view=self)

    async def on_timeout(self):
        self._revelar()
        if self.mensagem:
            e = self.mensagem.embeds[0]
            e.color = embeds.CINZA
            certa = self.pergunta["opcoes"][self.pergunta["certa"]]
            e.add_field(name="⏰ Tempo esgotado", value=f"Ninguém acertou. A resposta era **{certa}**.")
            try:
                await self.mensagem.edit(embed=e, view=self)
            except discord.HTTPException:
                pass


# ================================ FORCA ================================

class ModalLetra(discord.ui.Modal, title="Chutar uma letra"):
    letra = discord.ui.TextInput(label="Letra", min_length=1, max_length=1, placeholder="Ex.: A")

    def __init__(self, jogo_view: "ForcaView"):
        super().__init__()
        self.jogo_view = jogo_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.jogo_view.chute_letra(interaction, str(self.letra))


class ModalPalavra(discord.ui.Modal, title="Chutar a palavra inteira"):
    palavra = discord.ui.TextInput(label="Palavra (errar custa 2 vidas)", min_length=2, max_length=40)

    def __init__(self, jogo_view: "ForcaView"):
        super().__init__()
        self.jogo_view = jogo_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.jogo_view.chute_palavra(interaction, str(self.palavra))


class ForcaView(discord.ui.View):
    def __init__(self, bot, dono: discord.abc.User, jogo: Forca):
        super().__init__(timeout=300)
        self.bot = bot
        self.dono = dono
        self.jogo = jogo
        self.mensagem: Optional[discord.Message] = None

    def embed(self, rodape: Optional[str] = None) -> discord.Embed:
        j = self.jogo
        if j.ganhou:
            cor, titulo = embeds.VERDE, "🪢 Forca: palavra descoberta!"
        elif j.perdeu:
            cor, titulo = embeds.VERMELHO, "🪢 Forca: enforcado!"
        else:
            cor, titulo = embeds.AZUL, "🪢 Forca"
        e = discord.Embed(title=titulo, color=cor, description=DESENHOS[j.erros] + f"\n```{j.mascara}```")
        e.add_field(name="Dica", value=j.dica)
        e.add_field(name="Vidas", value="❤️" * (MAX_ERROS - j.erros) or "💀")
        e.add_field(name="Letras erradas", value=" ".join(l.upper() for l in j.erradas) or "nenhuma", inline=False)
        if rodape:
            e.set_footer(text=rodape)
        return e

    async def _atualizar(self, interaction: discord.Interaction, rodape: str):
        if self.jogo.acabou:
            self.stop()
            for item in self.children:
                item.disabled = True
            if self.jogo.perdeu:
                rodape = f"A palavra era {self.jogo.palavra}."
        await interaction.response.edit_message(embed=self.embed(rodape), view=self)

    async def chute_letra(self, interaction: discord.Interaction, letra: str):
        if self.jogo.acabou:
            return await interaction.response.send_message("Esse jogo já acabou.", ephemeral=True)
        resultado = self.jogo.chutar_letra(letra)
        if resultado == "invalida":
            return await interaction.response.send_message("Mande só uma letra, de A a Z.", ephemeral=True)
        if resultado == "repetida":
            return await interaction.response.send_message("Essa letra já foi tentada!", ephemeral=True)
        nome = interaction.user.display_name
        rodape = f"{nome} acertou a letra {letra.upper()}!" if resultado == "acerto" else f"{nome} errou a letra {letra.upper()}."
        if self.jogo.ganhou:
            await self.bot.db.add_coins(interaction.guild.id, interaction.user.id, PREMIO_FORCA_LETRA)
            rodape = f"{nome} completou a palavra e ganhou {PREMIO_FORCA_LETRA} {moeda.NOME}!"
        await self._atualizar(interaction, rodape)

    async def chute_palavra(self, interaction: discord.Interaction, chute: str):
        if self.jogo.acabou:
            return await interaction.response.send_message("Esse jogo já acabou.", ephemeral=True)
        nome = interaction.user.display_name
        if self.jogo.chutar_palavra(chute):
            await self.bot.db.add_coins(interaction.guild.id, interaction.user.id, PREMIO_FORCA_PALAVRA)
            rodape = f"{nome} acertou a palavra inteira e ganhou {PREMIO_FORCA_PALAVRA} {moeda.NOME}!"
        else:
            rodape = f"{nome} chutou \"{chute}\" e errou (-2 vidas)."
        await self._atualizar(interaction, rodape)

    @discord.ui.button(label="Chutar letra", emoji="🔤", style=discord.ButtonStyle.primary)
    async def botao_letra(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(ModalLetra(self))

    @discord.ui.button(label="Chutar palavra", emoji="💬", style=discord.ButtonStyle.secondary)
    async def botao_palavra(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(ModalPalavra(self))

    @discord.ui.button(label="Desistir", emoji="🏳️", style=discord.ButtonStyle.danger)
    async def botao_desistir(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.dono.id:
            return await interaction.response.send_message("Só quem começou o jogo pode desistir.", ephemeral=True)
        self.jogo.erros = MAX_ERROS
        await self._atualizar(interaction, "")

    async def on_timeout(self):
        if self.mensagem and not self.jogo.acabou:
            for item in self.children:
                item.disabled = True
            try:
                await self.mensagem.edit(embed=self.embed(f"⏰ Tempo esgotado. A palavra era {self.jogo.palavra}."),
                                         view=self)
            except discord.HTTPException:
                pass


# ============================ JOGO DA VELHA ============================

class CasaVelha(discord.ui.Button):
    def __init__(self, indice: int):
        super().__init__(label="​", style=discord.ButtonStyle.secondary, row=indice // 3)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction):
        await self.view.jogar(interaction, self.indice)


class VelhaView(discord.ui.View):
    def __init__(self, bot, jogador_x: discord.abc.User, jogador_o: discord.abc.User, contra_bot: bool,
                 dificuldade: str = "medio"):
        super().__init__(timeout=180)
        self.bot = bot
        self.jogadores = {"X": jogador_x, "O": jogador_o}
        self.contra_bot = contra_bot
        self.dificuldade = dificuldade
        self.vez = "X"
        self.tab: List[Optional[str]] = [None] * 9
        self.mensagem: Optional[discord.Message] = None
        self.casas = [CasaVelha(i) for i in range(9)]
        for casa in self.casas:
            self.add_item(casa)

    def texto(self, fim: Optional[str] = None) -> str:
        x, o = self.jogadores["X"].mention, self.jogadores["O"].mention
        cabecalho = f"❌ {x}  vs  ⭕ {o}"
        if self.contra_bot:
            cabecalho += f"  ·  dificuldade **{DIFICULDADES[self.dificuldade][0]}**"
        cabecalho += "\n\n"
        if fim == "empate":
            return cabecalho + "🤝 **Deu velha!** Empate."
        if fim:
            return cabecalho + f"🏆 **{self.jogadores[fim].mention} venceu!**"
        return cabecalho + f"Vez de {self.jogadores[self.vez].mention} ({'❌' if self.vez == 'X' else '⭕'})"

    def _marcar(self, indice: int, simbolo: str):
        self.tab[indice] = simbolo
        casa = self.casas[indice]
        casa.label = "X" if simbolo == "X" else "O"
        casa.style = discord.ButtonStyle.danger if simbolo == "X" else discord.ButtonStyle.success
        casa.disabled = True

    async def jogar(self, interaction: discord.Interaction, indice: int):
        if interaction.user.id != self.jogadores[self.vez].id:
            dono = interaction.user.id in (j.id for j in self.jogadores.values())
            aviso = "Calma, não é a sua vez!" if dono else "Você não está nesse jogo. Comece o seu com /velha!"
            return await interaction.response.send_message(aviso, ephemeral=True)

        self._marcar(indice, self.vez)
        fim = vencedor_velha(self.tab)
        if not fim:
            self.vez = "O" if self.vez == "X" else "X"
            if self.contra_bot:
                chance_de_errar = DIFICULDADES[self.dificuldade][1]
                self._marcar(jogada_do_bot(self.tab, "O", chance_de_errar), "O")
                fim = vencedor_velha(self.tab)
                self.vez = "X"

        extra = ""
        if fim:
            self.stop()
            for casa in self.casas:
                casa.disabled = True
            if self.contra_bot:
                _, _, premio_vitoria, premio_empate = DIFICULDADES[self.dificuldade]
                premio = premio_vitoria if fim == "X" else premio_empate if fim == "empate" else 0
                if premio:
                    await self.bot.db.add_coins(interaction.guild.id, self.jogadores["X"].id, premio)
                    extra = f"\nVocê ganhou {moeda.fmt(premio)}!"
        await interaction.response.edit_message(content=self.texto(fim) + extra, view=self)

    async def on_timeout(self):
        await _desativar(self, self.mensagem)


class ConviteVelha(discord.ui.View):
    """Convite para jogo da velha entre duas pessoas: o desafiado precisa aceitar."""

    def __init__(self, bot, desafiante: discord.abc.User, desafiado: discord.abc.User):
        super().__init__(timeout=60)
        self.bot = bot
        self.desafiante = desafiante
        self.desafiado = desafiado
        self.mensagem: Optional[discord.Message] = None
        self.respondido = False

    def texto(self) -> str:
        return (f"🎮 {self.desafiado.mention}, {self.desafiante.mention} te desafiou para um **jogo da velha**!\n"
                f"Você tem 60 segundos para aceitar.")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.desafiado.id:
            return True
        if interaction.user.id == self.desafiante.id:
            await interaction.response.send_message("Espere a outra pessoa responder ao convite.", ephemeral=True)
        else:
            await interaction.response.send_message("Esse convite não é para você.", ephemeral=True)
        return False

    @discord.ui.button(label="Aceitar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceitar(self, interaction: discord.Interaction, _):
        self.respondido = True
        self.stop()
        jogo = VelhaView(self.bot, self.desafiante, self.desafiado, contra_bot=False)
        jogo.mensagem = self.mensagem
        await interaction.response.edit_message(content=jogo.texto(), view=jogo)

    @discord.ui.button(label="Recusar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def recusar(self, interaction: discord.Interaction, _):
        self.respondido = True
        self.stop()
        await interaction.response.edit_message(
            content=f"{self.desafiado.mention} recusou o desafio de {self.desafiante.mention}.", view=None)

    async def on_timeout(self):
        if self.mensagem and not self.respondido:
            try:
                await self.mensagem.edit(
                    content=f"⏰ {self.desafiado.mention} não respondeu ao desafio de {self.desafiante.mention}.",
                    view=None)
            except discord.HTTPException:
                pass


# ======================= PEDRA, PAPEL E TESOURA =======================

EMOJIS_PPT = {"pedra": "🪨", "papel": "📄", "tesoura": "✂️"}


class PPTView(discord.ui.View):
    def __init__(self, bot, guild_id: int, jogador: discord.abc.User, aposta: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.jogador = jogador
        self.aposta = aposta
        self.jogou = False
        self.mensagem: Optional[discord.Message] = None
        for escolha, emoji in EMOJIS_PPT.items():
            botao = discord.ui.Button(label=escolha.capitalize(), emoji=emoji, style=discord.ButtonStyle.primary)
            botao.callback = self._fazer_callback(escolha)
            self.add_item(botao)

    def _fazer_callback(self, escolha: str):
        async def callback(interaction: discord.Interaction):
            await self.jogar(interaction, escolha)
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.jogador.id:
            await interaction.response.send_message("Esse jogo é de outra pessoa. Use /ppt para jogar!", ephemeral=True)
            return False
        return True

    async def jogar(self, interaction: discord.Interaction, escolha: str):
        if self.jogou:
            return
        self.jogou = True
        self.stop()
        bot_escolheu = random.choice(list(EMOJIS_PPT))
        resultado = resultado_ppt(escolha, bot_escolheu)
        g, u = self.guild_id, self.jogador.id

        linhas = [f"Você: {EMOJIS_PPT[escolha]} **{escolha}**", f"Eu: {EMOJIS_PPT[bot_escolheu]} **{bot_escolheu}**", ""]
        if resultado == "vitoria":
            cor = embeds.VERDE
            linhas.append("🏆 **Você venceu!**")
            if self.aposta:
                await self.bot.db.add_coins(g, u, self.aposta * 2)
                linhas.append(f"Ganhou {moeda.fmt(self.aposta * 2)}.")
        elif resultado == "derrota":
            cor = embeds.VERMELHO
            linhas.append("😎 **Eu venci!**")
            if self.aposta:
                linhas.append(f"Você perdeu {moeda.fmt(self.aposta)}.")
        else:
            cor = embeds.CINZA
            linhas.append("🤝 **Empate!**")
            if self.aposta:
                await self.bot.db.add_coins(g, u, self.aposta)
                linhas.append("Sua aposta foi devolvida.")

        for item in self.children:
            item.disabled = True
        e = discord.Embed(title="Pedra, papel e tesoura", color=cor, description="\n".join(linhas))
        await interaction.response.edit_message(embed=e, view=self)

    async def on_timeout(self):
        if not self.jogou and self.aposta:
            await self.bot.db.add_coins(self.guild_id, self.jogador.id, self.aposta)  # devolve a aposta
        await _desativar(self, self.mensagem)


# ================================ COG ================================

class Jogos(commands.Cog, name="Jogos"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="quiz", description=f"Pergunta valendo {PREMIO_QUIZ} {moeda.NOME}. Quem acertar primeiro leva!")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 15)
    async def quiz(self, interaction: discord.Interaction):
        pergunta = random.choice(PERGUNTAS)
        view = QuizView(self.bot, pergunta)
        e = discord.Embed(title=f"❓ Quiz · {pergunta['categoria']}", description=f"**{pergunta['pergunta']}**",
                          color=embeds.AZUL)
        e.set_footer(text=f"30 segundos · cada pessoa tem uma chance · vale {PREMIO_QUIZ} {moeda.NOME}")
        await interaction.response.send_message(embed=e, view=view)
        view.mensagem = await mensagem_duravel(interaction)

    @app_commands.command(name="forca", description="Jogo da forca. Todo mundo do canal pode ajudar a descobrir!")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 20)
    async def forca(self, interaction: discord.Interaction):
        categoria = random.choice(list(PALAVRAS))
        jogo = Forca(random.choice(PALAVRAS[categoria]), categoria)
        view = ForcaView(self.bot, interaction.user, jogo)
        await interaction.response.send_message(embed=view.embed("Use os botões para chutar."), view=view)
        view.mensagem = await mensagem_duravel(interaction)

    @app_commands.command(name="velha", description="Jogo da velha contra alguém (com convite) ou contra mim.")
    @app_commands.describe(oponente="Quem desafiar (vazio = jogar contra o bot)",
                           dificuldade="Dificuldade do bot (só vale contra o bot)")
    @app_commands.choices(dificuldade=[
        Choice(name="Fácil (vitória vale 50)", value="facil"),
        Choice(name="Médio (vitória vale 100)", value="medio"),
        Choice(name="Impossível (empate vale 60)", value="impossivel"),
    ])
    @app_commands.guild_only()
    async def velha(self, interaction: discord.Interaction, oponente: Optional[discord.Member] = None,
                    dificuldade: Optional[Choice[str]] = None):
        if oponente is not None and oponente.id != self.bot.user.id:
            if oponente.bot:
                return await interaction.response.send_message(
                    embed=embeds.erro("Esse bot não sabe jogar. Me desafie deixando o oponente vazio!"), ephemeral=True)
            if oponente.id == interaction.user.id:
                return await interaction.response.send_message(
                    embed=embeds.erro("Jogar contra você mesmo não vale!"), ephemeral=True)
            convite = ConviteVelha(self.bot, interaction.user, oponente)
            await interaction.response.send_message(
                convite.texto(), view=convite, allowed_mentions=discord.AllowedMentions(users=[oponente]))
            convite.mensagem = await mensagem_duravel(interaction)
            return

        nivel = dificuldade.value if dificuldade else "medio"
        view = VelhaView(self.bot, interaction.user, self.bot.user, contra_bot=True, dificuldade=nivel)
        _, _, premio_vitoria, premio_empate = DIFICULDADES[nivel]
        dica = (f"\nGanhe de mim e leve {moeda.fmt(premio_vitoria)}!" if premio_vitoria
                else f"\nNinguém ganha de mim aqui. Empate e leve {moeda.fmt(premio_empate)}!")
        await interaction.response.send_message(view.texto() + dica, view=view)
        view.mensagem = await mensagem_duravel(interaction)

    @app_commands.command(name="ppt", description="Pedra, papel e tesoura contra mim, com aposta opcional.")
    @app_commands.describe(aposta=f"Quanto apostar em {moeda.NOME} (opcional)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5)
    async def ppt(self, interaction: discord.Interaction, aposta: Optional[app_commands.Range[int, 1, 10_000_000]] = None):
        aposta = aposta or 0
        if aposta and not await self.bot.db.spend_coins(interaction.guild.id, interaction.user.id, aposta):
            return await interaction.response.send_message(
                embed=embeds.erro("Você não tem moedas suficientes para essa aposta."), ephemeral=True)
        view = PPTView(self.bot, interaction.guild.id, interaction.user, aposta)
        texto = "Escolha sua jogada!" + (f"\nAposta: {moeda.fmt(aposta)}" if aposta else "")
        await interaction.response.send_message(
            embed=discord.Embed(title="Pedra, papel e tesoura", description=texto, color=embeds.AZUL), view=view)
        view.mensagem = await mensagem_duravel(interaction)


async def setup(bot):
    await bot.add_cog(Jogos(bot))
