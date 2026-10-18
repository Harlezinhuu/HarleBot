"""Economia: moedas, daily, trabalho, apostas, loja de cargos e ranking."""
import random
import time
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds, moeda

DIA = 86400
HORA = 3600

DAILY_BASE = 200
DAILY_BONUS_POR_DIA = 25   # cada dia seguido soma isso...
DAILY_BONUS_MAXIMO = 10    # ...até 10 dias seguidos
TRABALHO_MIN, TRABALHO_MAX = 60, 160
APOSTA_MINIMA = 10
CHANCE_DE_GANHAR = 0.48   # cara ou coroa com 2% de vantagem da casa (igual cassino de verdade)

TRABALHOS = [
    "consertou o PC de um amigo",
    "fez entregas de bicicleta",
    "moderou um servidor gigante",
    "programou um site para uma padaria",
    "vendeu brigadeiro na escola",
    "fez uma live de 6 horas",
    "editou um vídeo para um youtuber",
    "deu aula de Minecraft para o primo",
    "otimizou o Windows de um cliente",
    "corrigiu um bug que ninguém achava",
]


def _relogio(segundos: int) -> str:
    h, resto = divmod(int(segundos), 3600)
    m = resto // 60
    if h:
        return f"{h}h {m}min"
    return f"{max(m, 1)}min"


class Economia(commands.Cog, name="Economia"):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ---------- carteira ----------

    @app_commands.command(name="saldo", description=f"Mostra quantas {moeda.NOME} você (ou outra pessoa) tem.")
    @app_commands.describe(membro="De quem ver o saldo")
    @app_commands.guild_only()
    async def saldo(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        membro = membro or interaction.user
        if membro.bot:
            return await interaction.response.send_message(embed=embeds.erro("Bots não têm carteira."), ephemeral=True)
        carteira = await self.db.get_wallet(interaction.guild.id, membro.id)
        e = discord.Embed(title=f"Carteira de {membro.display_name}", color=embeds.AMBAR,
                          description=moeda.fmt(carteira["coins"]))
        if carteira["streak"]:
            e.add_field(name="Daily seguido", value=f"🔥 {carteira['streak']} dias")
        e.set_thumbnail(url=membro.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="daily", description=f"Pega suas {moeda.NOME} do dia. Vindo todo dia, ganha bônus!")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction):
        agora = int(time.time())
        carteira = await self.db.get_wallet(interaction.guild.id, interaction.user.id)
        ultimo = carteira["last_daily"]

        if ultimo and agora - ultimo < DIA:
            falta = DIA - (agora - ultimo)
            return await interaction.response.send_message(
                embed=embeds.erro(f"Você já pegou o daily hoje. Volte em **{_relogio(falta)}**."), ephemeral=True)

        # Seguiu a sequência se voltou em até 48h
        streak = carteira["streak"] + 1 if ultimo and agora - ultimo < 2 * DIA else 1
        bonus = DAILY_BONUS_POR_DIA * (min(streak, DAILY_BONUS_MAXIMO) - 1)
        ganho = DAILY_BASE + bonus
        dobrou = await self.db.inv_use(interaction.guild.id, interaction.user.id, "boost_daily")
        if dobrou:
            ganho *= 2
        await self.db.set_daily(interaction.guild.id, interaction.user.id, agora, streak)
        saldo = await self.db.add_coins(interaction.guild.id, interaction.user.id, ganho)

        e = discord.Embed(title="🎁 Daily coletado!", color=embeds.VERDE,
                          description=f"Você ganhou {moeda.fmt(ganho)}.")
        e.add_field(name="Sequência", value=f"🔥 {streak} {'dia' if streak == 1 else 'dias'}")
        if bonus:
            e.add_field(name="Bônus da sequência", value=f"+{bonus}")
        if dobrou:
            e.add_field(name="🎁 Boost", value="Daily em dobro usado!")
        e.add_field(name="Saldo", value=moeda.fmt(saldo), inline=False)
        e.set_footer(text="Volte amanhã para manter a sequência!")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="trabalhar", description=f"Trabalha e ganha {moeda.NOME} (uma vez por hora).")
    @app_commands.guild_only()
    async def trabalhar(self, interaction: discord.Interaction):
        agora = int(time.time())
        carteira = await self.db.get_wallet(interaction.guild.id, interaction.user.id)
        if carteira["last_work"] and agora - carteira["last_work"] < HORA:
            falta = HORA - (agora - carteira["last_work"])
            return await interaction.response.send_message(
                embed=embeds.erro(f"Você está cansado. Descanse mais **{_relogio(falta)}**."), ephemeral=True)

        ganho = moeda.sorteio.randint(TRABALHO_MIN, TRABALHO_MAX)
        dobro = await self.db.boost_until(interaction.guild.id, interaction.user.id, "boost_trabalho") > agora
        if dobro:
            ganho *= 2
        await self.db.set_work(interaction.guild.id, interaction.user.id, agora)
        saldo = await self.db.add_coins(interaction.guild.id, interaction.user.id, ganho)
        e = discord.Embed(color=embeds.VERDE,
                          description=f"💼 Você {random.choice(TRABALHOS)} e ganhou {moeda.fmt(ganho)}.")
        e.set_footer(text=(f"Saldo: {saldo:,}".replace(",", ".")) + (" · 💼 salário em dobro ativo" if dobro else ""))
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="pagar", description=f"Manda {moeda.NOME} para outra pessoa.")
    @app_commands.describe(membro="Quem vai receber", quantidade="Quanto mandar")
    @app_commands.guild_only()
    async def pagar(self, interaction: discord.Interaction, membro: discord.Member,
                    quantidade: app_commands.Range[int, 1, 10_000_000]):
        if membro.bot or membro.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=embeds.erro("Escolha outra pessoa (que não seja um bot)."), ephemeral=True)
        if not await self.db.transfer(interaction.guild.id, interaction.user.id, membro.id, quantidade):
            return await interaction.response.send_message(
                embed=embeds.erro("Você não tem moedas suficientes."), ephemeral=True)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"{interaction.user.mention} mandou {moeda.fmt(quantidade)} para {membro.mention}."))

    @app_commands.command(name="apostar", description="Cara ou coroa: acertou, dobra a aposta (48% de chance). Errou, perde.")
    @app_commands.describe(quantidade="Quanto apostar", lado="Cara ou coroa?")
    @app_commands.choices(lado=[Choice(name="Cara", value="cara"), Choice(name="Coroa", value="coroa")])
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5)
    async def apostar(self, interaction: discord.Interaction,
                      quantidade: app_commands.Range[int, APOSTA_MINIMA, moeda.APOSTA_MAXIMA], lado: Choice[str]):
        if not await self.db.spend_coins(interaction.guild.id, interaction.user.id, quantidade):
            return await interaction.response.send_message(
                embed=embeds.erro("Você não tem moedas suficientes para essa aposta."), ephemeral=True)

        ganhou = moeda.sorteio.random() < CHANCE_DE_GANHAR
        outro = "coroa" if lado.value == "cara" else "cara"
        caiu = lado.value if ganhou else outro
        if ganhou:
            saldo = await self.db.add_coins(interaction.guild.id, interaction.user.id, quantidade * 2)
            e = discord.Embed(color=embeds.VERDE, title=f"🪙 Deu {caiu}! Você ganhou!",
                              description=f"Você levou {moeda.fmt(quantidade * 2)}.")
        else:
            saldo = (await self.db.get_wallet(interaction.guild.id, interaction.user.id))["coins"]
            e = discord.Embed(color=embeds.VERMELHO, title=f"🪙 Deu {caiu}. Não foi dessa vez.",
                              description=f"Você perdeu {moeda.fmt(quantidade)}.")
        e.set_footer(text=f"Saldo: {saldo:,}".replace(",", "."))
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="ranking-moedas", description=f"Quem tem mais {moeda.NOME} no servidor.")
    @app_commands.guild_only()
    async def ranking_moedas(self, interaction: discord.Interaction):
        top = await self.db.top_coins(interaction.guild.id)
        if not top:
            return await interaction.response.send_message(
                embed=embeds.erro("Ninguém tem moedas ainda. Use `/daily` para começar!"), ephemeral=True)
        medalhas = ["🥇", "🥈", "🥉"]
        linhas = [f"{medalhas[i] if i < 3 else f'`{i + 1}.`'} <@{r['user_id']}> · {r['coins']:,}".replace(",", ".")
                  for i, r in enumerate(top)]
        e = discord.Embed(title=f"{moeda.EMOJI} Ranking de {moeda.NOME}", color=embeds.AMBAR,
                          description="\n".join(linhas))
        await interaction.response.send_message(embed=e)

    # ---------- loja de cargos (a /loja e a /comprar ficam em cogs/perfil.py) ----------

    @app_commands.command(name="loja-adicionar", description="Coloca um cargo à venda na loja (ou muda o preço).")
    @app_commands.describe(cargo="Cargo para vender", preco="Preço em moedas")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def loja_adicionar(self, interaction: discord.Interaction, cargo: discord.Role,
                             preco: app_commands.Range[int, 1, 100_000_000]):
        if cargo.is_default() or cargo.managed:
            return await interaction.response.send_message(
                embed=embeds.erro("Esse cargo não pode ser vendido."), ephemeral=True)
        if cargo.permissions.administrator or cargo.permissions.manage_guild or cargo.permissions.ban_members:
            return await interaction.response.send_message(
                embed=embeds.erro("Por segurança, não dá para vender cargos com permissões de moderação."),
                ephemeral=True)
        await self.db.shop_add(interaction.guild.id, cargo.id, preco)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"{cargo.mention} está à venda por {moeda.fmt(preco)}."), ephemeral=True)

    @app_commands.command(name="loja-remover", description="Tira um cargo da loja.")
    @app_commands.describe(cargo="Cargo para tirar da loja")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def loja_remover(self, interaction: discord.Interaction, cargo: discord.Role):
        if await self.db.shop_remove(interaction.guild.id, cargo.id):
            await interaction.response.send_message(embed=embeds.sucesso(f"{cargo.mention} saiu da loja."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.erro("Esse cargo não estava na loja."), ephemeral=True)

    @app_commands.command(name="dar-moedas", description="(Só o dono do bot) Dá ou tira moedas de alguém.")
    @app_commands.describe(membro="Quem vai receber", quantidade="Quanto dar. Use negativo para tirar.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)  # esconde o comando de quem não é administrador
    async def dar_moedas(self, interaction: discord.Interaction, membro: discord.Member,
                         quantidade: app_commands.Range[int, -100_000_000, 100_000_000]):
        if not await self.bot.eh_dono(interaction.user):
            return await interaction.response.send_message(
                embed=embeds.erro("Só o dono do bot pode usar esse comando."), ephemeral=True)
        if membro.bot:
            return await interaction.response.send_message(embed=embeds.erro("Bots não têm carteira."), ephemeral=True)
        saldo = await self.db.add_coins(interaction.guild.id, membro.id, quantidade)
        await interaction.response.send_message(
            embed=embeds.sucesso(f"Saldo de {membro.mention} agora é {moeda.fmt(saldo)}."), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Economia(bot))
