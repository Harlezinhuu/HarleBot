"""Painéis de cargos no estilo Carl-bot: por reação ou por botão, e que funcionam mesmo após reiniciar."""
import re
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from utils import embeds

LIMITE_ITENS = 25
COR = embeds.AZUL


class BotaoCargo(discord.ui.DynamicItem[discord.ui.Button], template=r"hcargo:(?P<painel>\d+):(?P<cargo>\d+)"):
    """Botão "persistente": o custom_id guarda o painel e o cargo, então funciona até depois de reiniciar."""

    def __init__(self, painel_id: int, cargo_id: int, rotulo: Optional[str] = None, emoji: Optional[str] = None):
        super().__init__(discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.secondary,
                                           custom_id=f"hcargo:{painel_id}:{cargo_id}"))
        self.painel_id, self.cargo_id = painel_id, cargo_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match):
        return cls(int(match["painel"]), int(match["cargo"]), item.label, item.emoji)

    async def callback(self, interaction: discord.Interaction):
        cog: "Cargos" = interaction.client.get_cog("Cargos")
        texto = await cog.alternar_cargo(interaction.guild, interaction.user, self.painel_id, self.cargo_id)
        await interaction.response.send_message(texto, ephemeral=True)


def _emoji_valido(texto: Optional[str]) -> Optional[str]:
    """Aceita emoji comum (😀) ou do servidor (<:nome:123>). Devolve None se não parecer um emoji."""
    if not texto:
        return None
    texto = texto.strip()
    if re.fullmatch(r"<a?:\w{2,32}:\d{15,25}>", texto):
        return texto
    if len(texto) <= 8 and ("\u20e3" in texto or not any(c.isalnum() for c in texto)):  # 1️⃣ também vale
        return texto
    return None


class Cargos(commands.Cog, name="Cargos"):
    cargos = app_commands.Group(name="cargos", description="Painéis para os membros escolherem seus cargos.",
                                guild_only=True, default_permissions=discord.Permissions(manage_roles=True))

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_dynamic_items(BotaoCargo)

    async def cog_unload(self):
        self.bot.remove_dynamic_items(BotaoCargo)

    @property
    def db(self):
        return self.bot.db

    # ----- lógica -----

    def _problema_com_cargo(self, guild: discord.Guild, cargo: discord.Role) -> Optional[str]:
        if cargo.is_default() or cargo.managed:
            return "Esse cargo não pode ser entregue (é o @everyone ou de uma integração)."
        if cargo >= guild.me.top_role:
            return "Esse cargo está acima do meu. Suba o cargo do bot em Configurações do servidor → Cargos."
        p = cargo.permissions
        if p.administrator or p.manage_guild or p.manage_roles or p.ban_members or p.kick_members:
            return "Por segurança, não dá para colocar cargos com permissões de moderação num painel."
        return None

    async def alternar_cargo(self, guild: discord.Guild, membro: discord.Member, painel_id: int, cargo_id: int,
                             dar: Optional[bool] = None) -> str:
        """Dá ou tira o cargo. `dar=None` alterna (botão); True/False força (reações)."""
        painel = await self.db.painel(painel_id)
        cargo = guild.get_role(cargo_id)
        if painel is None or cargo is None:
            return "Esse painel ou cargo não existe mais."
        problema = self._problema_com_cargo(guild, cargo)
        if problema:
            return problema
        tem = cargo in membro.roles
        if dar is None:
            dar = not tem
        try:
            if dar and not tem:
                removidos = []
                if painel["unico"]:
                    outros = {i["role_id"] for i in await self.db.painel_itens(painel_id)} - {cargo_id}
                    removidos = [c for c in membro.roles if c.id in outros]
                    if removidos:
                        await membro.remove_roles(*removidos, reason="Painel de cargos (escolha única)")
                await membro.add_roles(cargo, reason="Painel de cargos")
                extra = f" (tirei {', '.join(c.mention for c in removidos)})" if removidos else ""
                return f"✅ Você ganhou o cargo {cargo.mention}{extra}."
            if not dar and tem:
                await membro.remove_roles(cargo, reason="Painel de cargos")
                return f"➖ Tirei o cargo {cargo.mention}."
            return "Nada mudou."
        except discord.Forbidden:
            return "Não tenho permissão para mexer nesse cargo. Avise a administração."

    async def _redesenhar(self, painel_id: int) -> Optional[str]:
        """Atualiza a mensagem do painel com a lista atual de cargos."""
        painel = await self.db.painel(painel_id)
        canal = self.bot.get_channel(painel["channel_id"])
        if canal is None:
            return "Não achei o canal do painel."
        itens = await self.db.painel_itens(painel_id)
        e = discord.Embed(title=painel["titulo"], description=painel["descricao"] or None, color=COR)
        linhas = []
        for item in itens:
            emoji = f"{item['emoji']} " if item["emoji"] else ""
            linhas.append(f"{emoji}<@&{item['role_id']}>" + (f" · {item['rotulo']}" if item["rotulo"] else ""))
        e.add_field(name="Cargos", value="\n".join(linhas) or "*Nenhum cargo ainda. Use `/cargos adicionar`.*",
                    inline=False)
        modo = "Clique num botão" if painel["modo"] == "botoes" else "Reaja com o emoji"
        e.set_footer(text=f"{modo} para pegar ou tirar o cargo." +
                     (" Só dá para ter um cargo deste painel." if painel["unico"] else ""))

        view = None
        if painel["modo"] == "botoes" and itens:
            view = discord.ui.View(timeout=None)
            for item in itens:
                cargo = canal.guild.get_role(item["role_id"])
                rotulo = item["rotulo"] or (cargo.name if cargo else "Cargo")
                view.add_item(BotaoCargo(painel_id, item["role_id"], rotulo[:80], item["emoji"]))
        try:
            mensagem = canal.get_partial_message(painel_id)
            await mensagem.edit(embed=e, view=view)
            if painel["modo"] == "reacoes":
                real = await canal.fetch_message(painel_id)
                atuais = {str(r.emoji) for r in real.reactions if r.me}
                for item in itens:
                    if item["emoji"] and item["emoji"] not in atuais:
                        await real.add_reaction(item["emoji"])
        except discord.NotFound:
            return "A mensagem do painel foi apagada."
        except discord.HTTPException as erro:
            return f"Não consegui atualizar o painel ({erro.text or erro.status})."
        return None

    async def _painel_do_servidor(self, interaction: discord.Interaction, mensagem_id: str):
        if not mensagem_id.strip().isdigit():
            await interaction.response.send_message(
                embed=embeds.erro("Cole o ID da mensagem do painel (botão direito → Copiar ID)."), ephemeral=True)
            return None
        painel = await self.db.painel(int(mensagem_id))
        if painel is None or painel["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(embed=embeds.erro("Não achei um painel com esse ID."),
                                                    ephemeral=True)
            return None
        return painel

    # ----- comandos -----

    @cargos.command(name="criar", description="Cria um painel de cargos num canal.")
    @app_commands.describe(canal="Onde o painel vai ficar", titulo="Título do painel", descricao="Texto explicando",
                           modo="Botões (moderno) ou reações (estilo Carl-bot)",
                           unico="Se sim, cada pessoa só pode ter um cargo deste painel")
    @app_commands.choices(modo=[Choice(name="Botões", value="botoes"), Choice(name="Reações", value="reacoes")])
    async def criar(self, interaction: discord.Interaction, canal: discord.TextChannel,
                    titulo: app_commands.Range[str, 1, 200], modo: Choice[str],
                    descricao: Optional[app_commands.Range[str, 1, 1000]] = None, unico: bool = False):
        perms = canal.permissions_for(interaction.guild.me)
        faltando = [nome for nome, ok in [("Ver canal", perms.view_channel), ("Enviar mensagens", perms.send_messages),
                                          ("Inserir links", perms.embed_links),
                                          ("Adicionar reações", perms.add_reactions or modo.value == "botoes")] if not ok]
        if faltando:
            return await interaction.response.send_message(
                embed=embeds.erro(f"Me falta permissão em {canal.mention}: {', '.join(faltando)}."), ephemeral=True)
        mensagem = await canal.send(embed=discord.Embed(title=titulo, description=descricao, color=COR))
        await self.db.painel_criar(mensagem.id, interaction.guild.id, canal.id, titulo, descricao, modo.value, unico)
        await self._redesenhar(mensagem.id)
        await interaction.response.send_message(embed=embeds.sucesso(
            f"Painel criado em {canal.mention}! ID: `{mensagem.id}`\n"
            f"Agora adicione cargos com `/cargos adicionar mensagem:{mensagem.id}`."), ephemeral=True)

    @cargos.command(name="adicionar", description="Coloca um cargo num painel.")
    @app_commands.describe(mensagem="ID da mensagem do painel", cargo="O cargo",
                           emoji="Emoji do cargo (obrigatório no modo reações)", rotulo="Texto do botão ou descrição")
    async def adicionar(self, interaction: discord.Interaction, mensagem: str, cargo: discord.Role,
                        emoji: Optional[str] = None, rotulo: Optional[app_commands.Range[str, 1, 80]] = None):
        painel = await self._painel_do_servidor(interaction, mensagem)
        if painel is None:
            return
        problema = self._problema_com_cargo(interaction.guild, cargo)
        if problema:
            return await interaction.response.send_message(embed=embeds.erro(problema), ephemeral=True)
        emoji_ok = _emoji_valido(emoji)
        if emoji and not emoji_ok:
            return await interaction.response.send_message(embed=embeds.erro("Esse emoji não é válido."),
                                                           ephemeral=True)
        if painel["modo"] == "reacoes" and not emoji_ok:
            return await interaction.response.send_message(
                embed=embeds.erro("No modo reações, todo cargo precisa de um emoji."), ephemeral=True)
        itens = await self.db.painel_itens(painel["message_id"])
        if len(itens) >= LIMITE_ITENS and all(i["role_id"] != cargo.id for i in itens):
            return await interaction.response.send_message(
                embed=embeds.erro(f"Um painel aceita até {LIMITE_ITENS} cargos. Crie outro painel."), ephemeral=True)
        if emoji_ok and any(i["emoji"] == emoji_ok and i["role_id"] != cargo.id for i in itens):
            return await interaction.response.send_message(
                embed=embeds.erro("Esse emoji já está sendo usado por outro cargo do painel."), ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await self.db.painel_item_salvar(painel["message_id"], cargo.id, emoji_ok, rotulo)
        erro = await self._redesenhar(painel["message_id"])
        if erro:
            return await interaction.followup.send(embed=embeds.erro(erro), ephemeral=True)
        await interaction.followup.send(embed=embeds.sucesso(f"{cargo.mention} foi para o painel."), ephemeral=True)

    @cargos.command(name="remover", description="Tira um cargo de um painel.")
    @app_commands.describe(mensagem="ID da mensagem do painel", cargo="O cargo")
    async def remover(self, interaction: discord.Interaction, mensagem: str, cargo: discord.Role):
        painel = await self._painel_do_servidor(interaction, mensagem)
        if painel is None:
            return
        itens = {i["role_id"]: i for i in await self.db.painel_itens(painel["message_id"])}
        if cargo.id not in itens:
            return await interaction.response.send_message(embed=embeds.erro("Esse cargo não está no painel."),
                                                           ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.db.painel_item_remover(painel["message_id"], cargo.id)
        if painel["modo"] == "reacoes" and itens[cargo.id]["emoji"]:
            canal = self.bot.get_channel(painel["channel_id"])
            try:
                msg = canal.get_partial_message(painel["message_id"])
                await msg.clear_reaction(itens[cargo.id]["emoji"])
            except (discord.HTTPException, AttributeError):
                pass
        await self._redesenhar(painel["message_id"])
        await interaction.followup.send(embed=embeds.sucesso(f"{cargo.mention} saiu do painel."), ephemeral=True)

    # ----- reações (modo Carl-bot) -----

    async def _reacao(self, payload: discord.RawReactionActionEvent, dar: bool):
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        painel = await self.db.painel(payload.message_id)
        if painel is None or painel["modo"] != "reacoes":
            return
        emoji = str(payload.emoji)
        item = next((i for i in await self.db.painel_itens(payload.message_id) if i["emoji"] == emoji), None)
        if item is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        membro = payload.member or (guild.get_member(payload.user_id) if guild else None)
        if guild is None or membro is None or membro.bot:
            return
        resultado = await self.alternar_cargo(guild, membro, payload.message_id, item["role_id"], dar=dar)
        if dar and painel["unico"] and resultado.startswith("✅"):
            # tira a reação dos outros emojis do painel, para refletir a escolha única
            canal = guild.get_channel(payload.channel_id)
            outros = [i["emoji"] for i in await self.db.painel_itens(payload.message_id)
                      if i["emoji"] and i["emoji"] != emoji]
            try:
                msg = canal.get_partial_message(payload.message_id)
                for e in outros:
                    await msg.remove_reaction(e, membro)
            except (discord.HTTPException, AttributeError):
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._reacao(payload, dar=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._reacao(payload, dar=False)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if await self.db.painel(payload.message_id):
            await self.db.painel_apagar(payload.message_id)


async def setup(bot):
    await bot.add_cog(Cargos(bot))
