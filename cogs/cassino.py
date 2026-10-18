"""Cassino: blackjack e campo minado, apostando Harlecoins."""
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds, moeda
from utils.cassino import CASAS_MINAS, Blackjack, Minas, mostrar, valor_mao
from utils.mensagens import mensagem_duravel

APOSTA_MINIMA = 10
APOSTA_MAXIMA = moeda.APOSTA_MAXIMA

RESULTADOS_BJ = {
    "blackjack": ("🃏 BLACKJACK!", embeds.VERDE),
    "vitoria": ("🏆 Você venceu!", embeds.VERDE),
    "empate": ("🤝 Empate, aposta devolvida.", embeds.CINZA),
    "derrota": ("😎 A mesa venceu.", embeds.VERMELHO),
    "estourou": ("💥 Estourou! Passou de 21.", embeds.VERMELHO),
}


# ============================== BLACKJACK ==============================

class BlackjackView(discord.ui.View):
    def __init__(self, bot, guild_id: int, jogador: discord.abc.User, jogo: Blackjack):
        super().__init__(timeout=90)
        self.bot = bot
        self.guild_id = guild_id
        self.jogador = jogador
        self.jogo = jogo
        self.mensagem: Optional[discord.Message] = None
        self.pago = False
        self._atualizar_botoes()

    def _atualizar_botoes(self):
        self.botao_dobrar.disabled = not self.jogo.pode_dobrar
        if self.jogo.acabou:
            for item in self.children:
                item.disabled = True

    def embed(self) -> discord.Embed:
        j = self.jogo
        if j.acabou:
            titulo, cor = RESULTADOS_BJ[j.resultado]
        else:
            titulo, cor = "🃏 Blackjack", embeds.AZUL
        e = discord.Embed(title=titulo, color=cor)
        e.add_field(name=f"Suas cartas · {valor_mao(j.jogador)}", value=mostrar(j.jogador), inline=False)
        mesa_valor = valor_mao(j.mesa) if j.acabou else "?"
        e.add_field(name=f"Mesa · {mesa_valor}", value=mostrar(j.mesa, esconder_segunda=not j.acabou), inline=False)
        aposta = f"Aposta: {moeda.fmt(j.aposta)}" + (" (dobrada)" if j.dobrou else "")
        if j.acabou:
            ganho = j.pagamento - j.aposta
            if ganho > 0:
                aposta += f"\nVocê ganhou {moeda.fmt(ganho)}!"
            elif ganho < 0:
                aposta += f"\nVocê perdeu {moeda.fmt(-ganho)}."
        e.add_field(name="​", value=aposta, inline=False)
        return e

    async def _pagar(self):
        if self.jogo.acabou and not self.pago:
            self.pago = True
            self.stop()
            if self.jogo.pagamento:
                await self.bot.db.add_coins(self.guild_id, self.jogador.id, self.jogo.pagamento)

    async def _responder(self, interaction: discord.Interaction):
        await self._pagar()
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.jogador.id:
            await interaction.response.send_message("Essa mesa é de outra pessoa. Use /blackjack!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pedir carta", emoji="➕", style=discord.ButtonStyle.primary)
    async def botao_pedir(self, interaction: discord.Interaction, _):
        self.jogo.pedir()
        await self._responder(interaction)

    @discord.ui.button(label="Parar", emoji="✋", style=discord.ButtonStyle.secondary)
    async def botao_parar(self, interaction: discord.Interaction, _):
        self.jogo.parar()
        await self._responder(interaction)

    @discord.ui.button(label="Dobrar", emoji="✖️", style=discord.ButtonStyle.success)
    async def botao_dobrar(self, interaction: discord.Interaction, _):
        if not await self.bot.db.spend_coins(self.guild_id, self.jogador.id, self.jogo.aposta):
            return await interaction.response.send_message("Você não tem moedas para dobrar.", ephemeral=True)
        self.jogo.dobrar()
        await self._responder(interaction)

    async def on_timeout(self):
        # Demorou demais: o bot para por você (sem perder a aposta à toa)
        if not self.jogo.acabou:
            self.jogo.parar()
        await self._pagar()
        self._atualizar_botoes()
        if self.mensagem:
            try:
                await self.mensagem.edit(embed=self.embed(), view=self)
            except discord.HTTPException:
                pass


# ============================ CAMPO MINADO ============================

class CasaMina(discord.ui.Button):
    def __init__(self, indice: int):
        super().__init__(label="​", style=discord.ButtonStyle.secondary, row=indice // 5)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction):
        await self.view.abrir(interaction, self.indice)


class MinasView(discord.ui.View):
    def __init__(self, bot, guild_id: int, jogador: discord.abc.User, jogo: Minas):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.jogador = jogador
        self.jogo = jogo
        self.mensagem: Optional[discord.Message] = None
        self.casas = [CasaMina(i) for i in range(CASAS_MINAS)]
        for casa in self.casas:
            self.add_item(casa)
        self.botao_sacar = discord.ui.Button(label="Sacar", emoji="💰", style=discord.ButtonStyle.success, row=4)
        self.botao_sacar.callback = self.sacar
        self.add_item(self.botao_sacar)
        self._atualizar_sacar()

    def _atualizar_sacar(self):
        if self.jogo.abertas:
            self.botao_sacar.label = f"Sacar {self.jogo.premio_atual:,}".replace(",", ".")
        else:
            self.botao_sacar.label = "Cancelar (devolve a aposta)"

    def embed(self, titulo: str = "💣 Campo minado", cor: int = embeds.AZUL) -> discord.Embed:
        j = self.jogo
        e = discord.Embed(title=titulo, color=cor)
        e.add_field(name="Aposta", value=moeda.fmt(j.aposta))
        e.add_field(name="Bombas", value=str(len(j.bombas)))
        e.add_field(name="Multiplicador", value=f"**{j.multiplicador:.2f}x**")
        if not j.acabou:
            e.add_field(name="Próxima casa vale", value=moeda.fmt(j.proximo_premio), inline=False)
            e.set_footer(text="Abra casas para aumentar o prêmio. Saque antes de achar uma bomba!")
        return e

    def _revelar_tudo(self):
        for casa in self.casas:
            casa.disabled = True
            if casa.indice in self.jogo.bombas:
                casa.emoji = "💣"
                casa.label = None
                if casa.indice == self.jogo.explodiu:
                    casa.style = discord.ButtonStyle.danger
            elif casa.indice not in self.jogo.abertas:
                casa.emoji = "💎"
                casa.label = None
        self.botao_sacar.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.jogador.id:
            await interaction.response.send_message("Esse campo é de outra pessoa. Use /minas!", ephemeral=True)
            return False
        return True

    async def abrir(self, interaction: discord.Interaction, indice: int):
        resultado = self.jogo.abrir(indice)
        if resultado == "ja_aberta":
            return await interaction.response.defer()

        casa = self.casas[indice]
        if resultado == "bomba":
            self.stop()
            self._revelar_tudo()
            e = self.embed("💥 BOOM! Você achou uma bomba.", embeds.VERMELHO)
            e.description = f"Perdeu {moeda.fmt(self.jogo.aposta)}."
            return await interaction.response.edit_message(embed=e, view=self)

        casa.emoji, casa.label = "💎", None
        casa.style = discord.ButtonStyle.success
        casa.disabled = True
        if resultado == "limpou":
            premio = self.jogo.premio_atual
            await self.bot.db.add_coins(self.guild_id, self.jogador.id, premio)
            self.stop()
            self._revelar_tudo()
            e = self.embed("🏆 Campo limpo! Você abriu todas as casas.", embeds.VERDE)
            e.description = f"Recebeu {moeda.fmt(premio)}!"
            return await interaction.response.edit_message(embed=e, view=self)

        self._atualizar_sacar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def sacar(self, interaction: discord.Interaction):
        if self.jogo.acabou:
            return await interaction.response.defer()
        cancelou = not self.jogo.abertas
        premio = self.jogo.sacar()
        await self.bot.db.add_coins(self.guild_id, self.jogador.id, premio)
        self.stop()
        self._revelar_tudo()
        if cancelou:
            e = self.embed("Jogo cancelado", embeds.CINZA)
            e.description = "Sua aposta foi devolvida."
        else:
            e = self.embed("💰 Sacou!", embeds.VERDE)
            e.description = f"Recebeu {moeda.fmt(premio)} (lucro de {moeda.fmt(premio - self.jogo.aposta)})."
        await interaction.response.edit_message(embed=e, view=self)

    async def on_timeout(self):
        # Demorou demais: saca automaticamente o que já tinha
        if self.jogo.acabou:
            return
        premio = self.jogo.sacar()
        await self.bot.db.add_coins(self.guild_id, self.jogador.id, premio)
        self._revelar_tudo()
        if self.mensagem:
            e = self.embed("⏰ Tempo esgotado: saque automático", embeds.CINZA)
            e.description = f"Recebeu {moeda.fmt(premio)}."
            try:
                await self.mensagem.edit(embed=e, view=self)
            except discord.HTTPException:
                pass


# ================================ COG ================================

class Cassino(commands.Cog, name="Cassino"):
    def __init__(self, bot):
        self.bot = bot

    async def _cobrar(self, interaction: discord.Interaction, aposta: int) -> bool:
        if await self.bot.db.spend_coins(interaction.guild.id, interaction.user.id, aposta):
            return True
        await interaction.response.send_message(
            embed=embeds.erro(f"Você não tem {moeda.fmt(aposta)}. Veja seu `/saldo`."), ephemeral=True)
        return False

    @app_commands.command(name="blackjack", description="Blackjack (21) contra a mesa, apostando Harlecoins.")
    @app_commands.describe(aposta="Quanto apostar")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5)
    async def blackjack(self, interaction: discord.Interaction,
                        aposta: app_commands.Range[int, APOSTA_MINIMA, APOSTA_MAXIMA]):
        if not await self._cobrar(interaction, aposta):
            return
        view = BlackjackView(self.bot, interaction.guild.id, interaction.user, Blackjack(aposta, moeda.sorteio))
        await view._pagar()  # se já saiu blackjack de cara, paga na hora
        view._atualizar_botoes()
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.mensagem = await mensagem_duravel(interaction)

    @app_commands.command(name="minas", description="Campo minado: abra casas para multiplicar a aposta. Saque antes da bomba!")
    @app_commands.describe(aposta="Quanto apostar", bombas="Quantas bombas (mais bombas = prêmio sobe mais rápido)")
    @app_commands.choices(bombas=[
        Choice(name="3 bombas (tranquilo)", value=3),
        Choice(name="5 bombas (arriscado)", value=5),
        Choice(name="8 bombas (insano)", value=8),
    ])
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5)
    async def minas(self, interaction: discord.Interaction,
                    aposta: app_commands.Range[int, APOSTA_MINIMA, APOSTA_MAXIMA],
                    bombas: Optional[Choice[int]] = None):
        if not await self._cobrar(interaction, aposta):
            return
        jogo = Minas(aposta, bombas.value if bombas else 3, moeda.sorteio)
        view = MinasView(self.bot, interaction.guild.id, interaction.user, jogo)
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.mensagem = await mensagem_duravel(interaction)


async def setup(bot):
    await bot.add_cog(Cassino(bot))
