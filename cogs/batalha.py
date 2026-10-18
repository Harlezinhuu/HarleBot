"""Batalha 1x1 por turnos entre dois membros, com aposta opcional."""
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds, moeda
from utils.batalha import VIDA_MAXIMA, Batalha, Lutador
from utils.niveis import barra
from utils.mensagens import mensagem_duravel

TEMPO_POR_TURNO = 60  # segundos; quem demorar perde


def _vida(l: Lutador) -> str:
    coracao = "🛡️" if l.defendendo else "❤️"
    return f"{coracao} {barra(l.vida, VIDA_MAXIMA, 10)} **{l.vida}**/{VIDA_MAXIMA}"


class BatalhaView(discord.ui.View):
    def __init__(self, bot, guild_id: int, membros, batalha: Batalha, aposta: int):
        super().__init__(timeout=TEMPO_POR_TURNO)
        self.bot = bot
        self.guild_id = guild_id
        self.membros = {m.id: m for m in membros}
        self.batalha = batalha
        self.aposta = aposta
        self.mensagem: Optional[discord.Message] = None
        self.pago = False
        self._atualizar_botoes()

    def _atualizar_botoes(self):
        atual = self.batalha.atual
        self.botao_especial.disabled = not atual.especial_pronto
        self.botao_curar.label = f"Curar ({atual.curas})"
        self.botao_curar.disabled = atual.curas <= 0
        if self.batalha.acabou:
            for item in self.children:
                item.disabled = True

    def embed(self, rodape: Optional[str] = None) -> discord.Embed:
        b = self.batalha
        a, c = b.lutadores
        if b.acabou:
            e = discord.Embed(title=f"🏆 {b.vencedor.nome} venceu a batalha!", color=embeds.VERDE)
        else:
            e = discord.Embed(title="⚔️ Batalha", color=embeds.VERMELHO,
                              description=f"Turno {b.turno} · vez de <@{b.atual.uid}>")
        e.add_field(name=a.nome, value=_vida(a), inline=False)
        e.add_field(name=c.nome, value=_vida(c), inline=False)
        if b.historico:
            e.add_field(name="Últimas jogadas", value="\n".join(b.historico[-3:]), inline=False)
        if self.aposta:
            e.add_field(name="Em jogo", value=moeda.fmt(self.aposta * 2), inline=False)
        if rodape:
            e.set_footer(text=rodape)
        elif not b.acabou:
            e.set_footer(text=f"Cada um tem {TEMPO_POR_TURNO}s por turno. Quem demorar perde.")
        return e

    async def _pagar(self) -> str:
        if self.pago or not self.batalha.acabou:
            return ""
        self.pago = True
        self.stop()
        if self.aposta:
            await self.bot.db.add_coins(self.guild_id, self.batalha.vencedor.uid, self.aposta * 2)
            return f"{self.batalha.vencedor.nome} levou {self.aposta * 2:,} {moeda.NOME}!".replace(",", ".")
        return ""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.membros:
            await interaction.response.send_message("Você não está nessa batalha. Desafie alguém com /batalha!",
                                                    ephemeral=True)
            return False
        if interaction.user.id != self.batalha.atual.uid:
            await interaction.response.send_message("Calma, é a vez do outro!", ephemeral=True)
            return False
        return True

    async def _agir(self, interaction: discord.Interaction, acao: str):
        texto = self.batalha.agir(acao)
        if texto in ("O especial ainda está carregando.", "Acabaram as curas.", "Ação inválida."):
            return await interaction.response.send_message(texto, ephemeral=True)
        rodape = await self._pagar()
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.embed(rodape or None), view=self)

    @discord.ui.button(label="Atacar", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def botao_atacar(self, interaction: discord.Interaction, _):
        await self._agir(interaction, "atacar")

    @discord.ui.button(label="Especial", emoji="💥", style=discord.ButtonStyle.primary)
    async def botao_especial(self, interaction: discord.Interaction, _):
        await self._agir(interaction, "especial")

    @discord.ui.button(label="Defender", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def botao_defender(self, interaction: discord.Interaction, _):
        await self._agir(interaction, "defender")

    @discord.ui.button(label="Curar", emoji="🧪", style=discord.ButtonStyle.success)
    async def botao_curar(self, interaction: discord.Interaction, _):
        await self._agir(interaction, "curar")

    @discord.ui.button(label="Desistir", emoji="🏳️", style=discord.ButtonStyle.secondary, row=1)
    async def botao_desistir(self, interaction: discord.Interaction, _):
        self.batalha.desistencia(interaction.user.id)
        rodape = await self._pagar()
        self._atualizar_botoes()
        await interaction.response.edit_message(
            embed=self.embed(f"{interaction.user.display_name} desistiu. {rodape}".strip()), view=self)

    async def on_timeout(self):
        if self.batalha.acabou:
            return
        demorou = self.batalha.atual
        self.batalha.desistencia(demorou.uid)
        rodape = await self._pagar()
        self._atualizar_botoes()
        if self.mensagem:
            try:
                await self.mensagem.edit(embed=self.embed(f"⏰ {demorou.nome} demorou demais e perdeu. {rodape}".strip()),
                                         view=self)
            except discord.HTTPException:
                pass


class ConviteBatalha(discord.ui.View):
    def __init__(self, bot, guild_id: int, desafiante: discord.Member, desafiado: discord.Member, aposta: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.desafiante = desafiante
        self.desafiado = desafiado
        self.aposta = aposta
        self.mensagem: Optional[discord.Message] = None
        self.respondido = False

    def texto(self) -> str:
        valendo = f" valendo {moeda.fmt(self.aposta)} de cada um" if self.aposta else ""
        return (f"⚔️ {self.desafiado.mention}, {self.desafiante.mention} te desafiou para uma **batalha**{valendo}!\n"
                f"Você tem 60 segundos para aceitar.")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.desafiado.id:
            return True
        aviso = ("Espere a outra pessoa responder." if interaction.user.id == self.desafiante.id
                 else "Esse desafio não é para você.")
        await interaction.response.send_message(aviso, ephemeral=True)
        return False

    async def _devolver_desafiante(self):
        if self.aposta:
            await self.bot.db.add_coins(self.guild_id, self.desafiante.id, self.aposta)

    @discord.ui.button(label="Aceitar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceitar(self, interaction: discord.Interaction, _):
        if self.aposta and not await self.bot.db.spend_coins(self.guild_id, self.desafiado.id, self.aposta):
            return await interaction.response.send_message(
                f"Você precisa de {moeda.fmt(self.aposta)} para aceitar.", ephemeral=True)
        self.respondido = True
        self.stop()
        batalha = Batalha(Lutador(self.desafiante.id, self.desafiante.display_name),
                          Lutador(self.desafiado.id, self.desafiado.display_name))
        view = BatalhaView(self.bot, self.guild_id, [self.desafiante, self.desafiado], batalha, self.aposta)
        view.mensagem = self.mensagem
        await interaction.response.edit_message(content=None, embed=view.embed(), view=view)

    @discord.ui.button(label="Recusar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def recusar(self, interaction: discord.Interaction, _):
        self.respondido = True
        self.stop()
        await self._devolver_desafiante()
        await interaction.response.edit_message(
            content=f"{self.desafiado.mention} recusou a batalha contra {self.desafiante.mention}.", view=None)

    async def on_timeout(self):
        if self.respondido:
            return
        await self._devolver_desafiante()
        if self.mensagem:
            try:
                await self.mensagem.edit(
                    content=f"⏰ {self.desafiado.mention} não respondeu ao desafio de {self.desafiante.mention}.",
                    view=None)
            except discord.HTTPException:
                pass


class BatalhaCog(commands.Cog, name="Batalha"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="batalha", description="Desafia alguém para uma batalha por turnos, com aposta opcional.")
    @app_commands.describe(oponente="Quem desafiar", aposta=f"Quanto cada um aposta em {moeda.NOME} (opcional)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    async def batalha(self, interaction: discord.Interaction, oponente: discord.Member,
                      aposta: Optional[app_commands.Range[int, 1, 10_000_000]] = None):
        if oponente.bot or oponente.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=embeds.erro("Escolha outra pessoa (que não seja um bot)."), ephemeral=True)
        aposta = aposta or 0
        if aposta and not await self.bot.db.spend_coins(interaction.guild.id, interaction.user.id, aposta):
            return await interaction.response.send_message(
                embed=embeds.erro(f"Você não tem {moeda.fmt(aposta)}."), ephemeral=True)
        convite = ConviteBatalha(self.bot, interaction.guild.id, interaction.user, oponente, aposta)
        await interaction.response.send_message(
            convite.texto(), view=convite, allowed_mentions=discord.AllowedMentions(users=[oponente]))
        convite.mensagem = await mensagem_duravel(interaction)


async def setup(bot):
    await bot.add_cog(BatalhaCog(bot))
