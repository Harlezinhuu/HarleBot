"""Loja de itens (temas, insígnias, títulos, boosts e cargos), inventário e perfil."""
import time
from datetime import datetime, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from conteudo.itens import CATEGORIAS, ITENS, eh_consumivel, rotulo
from utils import embeds, moeda
from utils.jogos import sem_acento
from utils.niveis import barra, nivel_de

LIMITE_SOBRE_MIM = 200


def _preco(valor: int) -> str:
    return f"{moeda.EMOJI} {valor:,}".replace(",", ".")


def _tempo_restante(segundos: int) -> str:
    h, resto = divmod(max(int(segundos), 0), 3600)
    m = resto // 60
    return f"{h}h {m}min" if h else f"{max(m, 1)}min"


# ================================ LOJA ================================

class LojaView(discord.ui.View):
    def __init__(self, bot, interaction: discord.Interaction, possui: set):
        super().__init__(timeout=180)
        self.bot = bot
        self.dono_id = interaction.user.id
        self.guild = interaction.guild
        self.possui = possui
        self.mensagem: Optional[discord.Message] = None
        for chave, (emoji, nome) in CATEGORIAS.items():
            self._botao(chave, emoji, nome.split(" ")[0])
        self._botao("cargos", "🎭", "Cargos")

    def _botao(self, chave: str, emoji: str, nome: str):
        botao = discord.ui.Button(label=nome, emoji=emoji, style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(embed=await self.pagina(chave), view=self)

        botao.callback = callback
        self.add_item(botao)

    async def pagina(self, chave: str) -> discord.Embed:
        if chave == "cargos":
            e = discord.Embed(title="🎭 Cargos do servidor", color=embeds.AZUL)
            linhas = []
            for item in await self.bot.db.shop_list(self.guild.id):
                cargo = self.guild.get_role(item["role_id"])
                if cargo:
                    linhas.append(f"{cargo.mention} · {_preco(item['price'])}")
            e.description = "\n".join(linhas) or "A administração ainda não colocou cargos à venda (`/loja-adicionar`)."
        else:
            emoji, nome = CATEGORIAS[chave]
            e = discord.Embed(title=f"{emoji} {nome}", color=embeds.AZUL)
            linhas = []
            for item_id, item in ITENS.items():
                if item["categoria"] != chave:
                    continue
                tem = " ✅" if item_id in self.possui and not eh_consumivel(item_id) else ""
                linhas.append(f"{item['emoji']} **{item['nome']}** · {_preco(item['preco'])}{tem}")
            e.description = "\n".join(linhas)
            if chave == "tema":
                e.set_footer(text="O tema muda a cor e o emoji do seu /perfil.")
            elif chave == "boost":
                e.set_footer(text="Boosts são usados com /usar (o daily em dobro é usado sozinho).")
        e.set_author(name="Loja do Harle Bot")
        e.add_field(name="​", value="Compre com `/comprar` · veja seus itens em `/inventario`", inline=False)
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.dono_id:
            await interaction.response.send_message("Abra a sua própria loja com /loja!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.mensagem:
            try:
                await self.mensagem.edit(view=self)
            except discord.HTTPException:
                pass


# ================================ COG ================================

class Perfil(commands.Cog, name="Loja e Perfil"):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def _possui(self, guild_id: int, user_id: int) -> set:
        return {r["item_id"] for r in await self.db.inv_list(guild_id, user_id)}

    # ---------- loja ----------

    @app_commands.command(name="loja", description="Abre a loja: temas, insígnias, títulos, boosts e cargos.")
    @app_commands.guild_only()
    async def loja(self, interaction: discord.Interaction):
        view = LojaView(self.bot, interaction, await self._possui(interaction.guild.id, interaction.user.id))
        await interaction.response.send_message(embed=await view.pagina("tema"), view=view)
        view.mensagem = await interaction.original_response()

    @app_commands.command(name="comprar", description="Compra um item ou cargo da loja.")
    @app_commands.describe(item="Comece a digitar o nome do item")
    @app_commands.guild_only()
    async def comprar(self, interaction: discord.Interaction, item: str):
        g, u = interaction.guild.id, interaction.user.id

        # ----- cargo do servidor -----
        if item.startswith("cargo:"):
            cargo = interaction.guild.get_role(int(item.split(":", 1)[1])) if item[6:].isdigit() else None
            oferta = await self.db.shop_get(g, cargo.id) if cargo else None
            if oferta is None:
                return await interaction.response.send_message(embed=embeds.erro("Esse cargo não está à venda."),
                                                               ephemeral=True)
            if cargo in interaction.user.roles:
                return await interaction.response.send_message(embed=embeds.erro("Você já tem esse cargo."),
                                                               ephemeral=True)
            me = interaction.guild.me
            if not me.guild_permissions.manage_roles or cargo >= me.top_role:
                return await interaction.response.send_message(
                    embed=embeds.erro("Não consigo entregar esse cargo agora. Avise a administração."), ephemeral=True)
            if not await self.db.spend_coins(g, u, oferta["price"]):
                return await interaction.response.send_message(
                    embed=embeds.erro(f"Você precisa de {moeda.fmt(oferta['price'])}."), ephemeral=True)
            try:
                await interaction.user.add_roles(cargo, reason="Comprado na loja do Harle Bot")
            except discord.HTTPException:
                await self.db.add_coins(g, u, oferta["price"])
                return await interaction.response.send_message(
                    embed=embeds.erro("Não consegui entregar o cargo. Suas moedas foram devolvidas."), ephemeral=True)
            return await interaction.response.send_message(
                embed=embeds.sucesso(f"{interaction.user.mention} comprou o cargo {cargo.mention}!"))

        # ----- item do bot -----
        item_id = item.removeprefix("item:")
        dados = ITENS.get(item_id)
        if dados is None:
            return await interaction.response.send_message(
                embed=embeds.erro("Não achei esse item. Escolha um da lista que aparece ao digitar."), ephemeral=True)
        if not eh_consumivel(item_id) and await self.db.inv_count(g, u, item_id):
            return await interaction.response.send_message(embed=embeds.erro("Você já tem esse item."), ephemeral=True)
        if not await self.db.spend_coins(g, u, dados["preco"]):
            return await interaction.response.send_message(
                embed=embeds.erro(f"Você precisa de {moeda.fmt(dados['preco'])} para comprar isso."), ephemeral=True)
        await self.db.inv_add(g, u, item_id)

        dica = {
            "tema": "Equipe com `/usar`.",
            "titulo": "Equipe com `/usar`.",
            "insignia": "Ela já aparece no seu `/perfil`.",
            "boost": "Ative com `/usar`." if item_id != "boost_daily" else "Ele vale no seu próximo `/daily`.",
        }[dados["categoria"]]
        await interaction.response.send_message(
            embed=embeds.sucesso(f"Você comprou **{rotulo(item_id)}** por {moeda.fmt(dados['preco'])}. {dica}"))

    @comprar.autocomplete("item")
    async def comprar_autocomplete(self, interaction: discord.Interaction, atual: str):
        atual = sem_acento(atual)
        opcoes: List[app_commands.Choice[str]] = []
        for item_id, item in ITENS.items():
            # dá para buscar pelo nome ou pela categoria ("tema", "insignia", "titulo", "boost")
            if atual in sem_acento(f"{item['nome']} {item['categoria']} {CATEGORIAS[item['categoria']][1]}"):
                opcoes.append(app_commands.Choice(name=f"{item['emoji']} {item['nome']} · {item['preco']}",
                                                  value=f"item:{item_id}"))
        if interaction.guild:
            for oferta in await self.db.shop_list(interaction.guild.id):
                cargo = interaction.guild.get_role(oferta["role_id"])
                if cargo and (atual in sem_acento(cargo.name) or atual in "cargo"):
                    opcoes.append(app_commands.Choice(name=f"🎭 Cargo {cargo.name} · {oferta['price']}"[:100],
                                                      value=f"cargo:{cargo.id}"))
        return opcoes[:25]

    # ---------- inventário e uso ----------

    @app_commands.command(name="inventario", description="Mostra seus itens e boosts ativos.")
    @app_commands.guild_only()
    async def inventario(self, interaction: discord.Interaction):
        g, u = interaction.guild.id, interaction.user.id
        itens = await self.db.inv_list(g, u)
        _, tema, titulo = await self.db.profile_get(g, u)
        e = discord.Embed(title=f"🎒 Inventário de {interaction.user.display_name}", color=embeds.AZUL)
        for chave, (emoji, nome) in CATEGORIAS.items():
            linhas = []
            for r in itens:
                if r["item_id"] not in ITENS or ITENS[r["item_id"]]["categoria"] != chave:
                    continue
                texto = rotulo(r["item_id"])
                if eh_consumivel(r["item_id"]):
                    texto += f" ×{r['quantity']}"
                if r["item_id"] in (tema, titulo):
                    texto += " *(equipado)*"
                linhas.append(texto)
            if linhas:
                e.add_field(name=f"{emoji} {nome}", value="\n".join(linhas), inline=False)
        ativos = await self._boosts_ativos(g, u)
        if ativos:
            e.add_field(name="⏳ Boosts ativos", value="\n".join(ativos), inline=False)
        if not e.fields:
            e.description = "Vazio por enquanto. Dê uma olhada na `/loja`!"
        else:
            e.set_footer(text="Equipe temas e títulos ou ative boosts com /usar")
        await interaction.response.send_message(embed=e, ephemeral=True)

    async def _boosts_ativos(self, g: int, u: int) -> List[str]:
        agora = time.time()
        ativos = []
        for item_id in ("boost_xp", "boost_trabalho"):
            ate = await self.db.boost_until(g, u, item_id)
            if ate > agora:
                ativos.append(f"{rotulo(item_id)}: falta {_tempo_restante(ate - agora)}")
        return ativos

    @app_commands.command(name="usar", description="Equipa um tema ou título, ou ativa um boost.")
    @app_commands.describe(item="Comece a digitar o nome do item")
    @app_commands.guild_only()
    async def usar(self, interaction: discord.Interaction, item: str):
        g, u = interaction.guild.id, interaction.user.id
        if item in ("tirar:tema", "tirar:titulo"):
            campo = "theme" if item == "tirar:tema" else "title"
            await self.db.profile_set(g, u, campo, None)
            nome = "tema" if campo == "theme" else "título"
            return await interaction.response.send_message(embed=embeds.sucesso(f"Você tirou o {nome}."), ephemeral=True)

        item_id = item.removeprefix("item:")
        dados = ITENS.get(item_id)
        if dados is None or not await self.db.inv_count(g, u, item_id):
            return await interaction.response.send_message(
                embed=embeds.erro("Você não tem esse item. Veja o `/inventario`."), ephemeral=True)

        categoria = dados["categoria"]
        if categoria in ("tema", "titulo"):
            await self.db.profile_set(g, u, "theme" if categoria == "tema" else "title", item_id)
            texto = f"Agora você está usando **{rotulo(item_id)}**. Veja no `/perfil`!"
        elif categoria == "insignia":
            texto = "Insígnias aparecem sozinhas no seu `/perfil`, não precisa usar."
        elif item_id == "boost_daily":
            texto = "Esse boost é usado sozinho no seu próximo `/daily`."
        else:
            await self.db.inv_use(g, u, item_id)
            ate = await self.db.boost_activate(g, u, item_id, dados["duracao"], int(time.time()))
            termina = datetime.fromtimestamp(ate, tz=timezone.utc)
            texto = f"**{rotulo(item_id)}** ativado! Acaba {discord.utils.format_dt(termina, 'R')}."
        await interaction.response.send_message(embed=embeds.sucesso(texto), ephemeral=True)

    @usar.autocomplete("item")
    async def usar_autocomplete(self, interaction: discord.Interaction, atual: str):
        if not interaction.guild:
            return []
        atual = atual.lower()
        g, u = interaction.guild.id, interaction.user.id
        _, tema, titulo = await self.db.profile_get(g, u)
        opcoes = []
        for r in await self.db.inv_list(g, u):
            item_id = r["item_id"]
            if item_id not in ITENS or ITENS[item_id]["categoria"] == "insignia":
                continue
            if atual in ITENS[item_id]["nome"].lower():
                extra = f" ×{r['quantity']}" if eh_consumivel(item_id) else ""
                opcoes.append(app_commands.Choice(name=f"{rotulo(item_id)}{extra}"[:100], value=f"item:{item_id}"))
        quer_tirar = not atual or "tirar" in atual
        if tema and quer_tirar:
            opcoes.append(app_commands.Choice(name="❌ Tirar o tema", value="tirar:tema"))
        if titulo and quer_tirar:
            opcoes.append(app_commands.Choice(name="❌ Tirar o título", value="tirar:titulo"))
        return opcoes[:25]

    # ---------- perfil ----------

    @app_commands.command(name="perfil", description="Mostra o perfil com tema, título, insígnias, nível e moedas.")
    @app_commands.describe(membro="De quem ver o perfil")
    @app_commands.guild_only()
    async def perfil(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        membro = membro or interaction.user
        if membro.bot:
            return await interaction.response.send_message(embed=embeds.erro("Bots não têm perfil."), ephemeral=True)
        g, u = interaction.guild.id, membro.id
        sobre, tema, titulo = await self.db.profile_get(g, u)
        carteira = await self.db.get_wallet(g, u)
        xp = await self.db.get_xp(g, u)
        nivel, atual, precisa = nivel_de(xp)
        posicao = await self.db.xp_rank(g, u)
        insignias = [ITENS[r["item_id"]]["emoji"] for r in await self.db.inv_list(g, u)
                     if r["item_id"] in ITENS and ITENS[r["item_id"]]["categoria"] == "insignia"]

        cor = ITENS[tema]["cor"] if tema in ITENS else embeds.AZUL
        emoji_tema = ITENS[tema]["emoji"] + " " if tema in ITENS else ""
        e = discord.Embed(title=f"{emoji_tema}{membro.display_name}", color=cor)
        partes = []
        if titulo in ITENS:
            partes.append(f"*{rotulo(titulo)}*")
        partes.append(sobre or "*Sem \"sobre mim\" ainda. Use `/sobremim` para escrever o seu.*")
        e.description = "\n\n".join(partes)
        e.add_field(name="Nível", value=f"**{nivel}** · #{posicao} no servidor")
        e.add_field(name=moeda.NOME, value=f"{moeda.EMOJI} {carteira['coins']:,}".replace(",", "."))
        e.add_field(name="Daily seguido", value=f"🔥 {carteira['streak']}")
        e.add_field(name=f"Progresso para o nível {nivel + 1}", value=f"{barra(atual, precisa)} {atual}/{precisa}",
                    inline=False)
        if insignias:
            e.add_field(name="Insígnias", value=" ".join(insignias), inline=False)
        ativos = await self._boosts_ativos(g, u)
        if ativos:
            e.add_field(name="Boosts ativos", value="\n".join(ativos), inline=False)
        e.set_thumbnail(url=membro.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="sobremim", description="Escreve o texto que aparece no seu /perfil.")
    @app_commands.describe(texto=f"Até {LIMITE_SOBRE_MIM} caracteres (deixe vazio para apagar)")
    @app_commands.guild_only()
    async def sobremim(self, interaction: discord.Interaction,
                       texto: Optional[app_commands.Range[str, 1, LIMITE_SOBRE_MIM]] = None):
        await self.db.profile_set(interaction.guild.id, interaction.user.id, "about", texto)
        msg = "Seu \"sobre mim\" foi atualizado!" if texto else "Seu \"sobre mim\" foi apagado."
        await interaction.response.send_message(embed=embeds.sucesso(msg), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Perfil(bot))
