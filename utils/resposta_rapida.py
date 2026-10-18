"""Proteção contra "O aplicativo não respondeu".

O Discord exige que todo comando ou botão seja respondido em até 3 segundos. Se o servidor estiver
lento, esta proteção avisa o Discord que o bot está processando ("pensando...") depois de 2 segundos,
o que dá até 15 minutos para terminar. As respostas que o comando mandar depois disso são
redirecionadas automaticamente, então nenhum comando precisa ser alterado.
"""
import asyncio
import logging

import discord

log = logging.getLogger("harle.resposta")
ESPERA = 2.0
_CHAVE = "harle_adiado"

_enviar_original = discord.InteractionResponse.send_message
_editar_original = discord.InteractionResponse.edit_message
_adiar_original = discord.InteractionResponse.defer


async def _enviar(self: discord.InteractionResponse, *args, **kwargs):
    interacao = self._parent
    if interacao.extras.get(_CHAVE):
        kwargs.pop("delete_after", None)
        if "view" in kwargs and kwargs["view"] is None:
            kwargs.pop("view")
        return await interacao.followup.send(*args, **kwargs)
    return await _enviar_original(self, *args, **kwargs)


async def _editar(self: discord.InteractionResponse, **kwargs):
    interacao = self._parent
    if interacao.extras.get(_CHAVE):
        kwargs.pop("delete_after", None)
        return await interacao.edit_original_response(**kwargs)
    return await _editar_original(self, **kwargs)


async def _adiar(self: discord.InteractionResponse, *args, **kwargs):
    if self._parent.extras.get(_CHAVE):
        return None  # já foi adiado pela proteção
    return await _adiar_original(self, *args, **kwargs)


async def _vigiar(interacao: discord.Interaction):
    await asyncio.sleep(ESPERA)
    if interacao.response.is_done():
        return
    try:
        interacao.extras[_CHAVE] = True
        if interacao.type == discord.InteractionType.component:
            await _adiar_original(interacao.response)                  # "atualizando a mensagem..."
        elif interacao.type == discord.InteractionType.application_command:
            await _adiar_original(interacao.response, thinking=True)   # "Harle Bot está pensando..."
        else:
            interacao.extras[_CHAVE] = False
            return
        nome = interacao.command.name if interacao.command else interacao.data.get("custom_id", "?")
        log.info("Resposta lenta em %s: adiada automaticamente", nome)
    except discord.InteractionResponded:
        interacao.extras[_CHAVE] = False   # o comando respondeu bem nessa hora
    except discord.HTTPException as erro:
        interacao.extras[_CHAVE] = False
        log.warning("Não consegui adiar a resposta: %s", erro)


def _botao_sem_dono(bot: discord.Client, interacao: discord.Interaction) -> bool:
    """True se o botão/menu clicado é de um jogo que não existe mais (o bot reiniciou ou o jogo acabou)."""
    try:
        loja = bot._connection._view_store  # interno do discord.py; se mudar, só não avisa
        chave = (interacao.data["component_type"], interacao.data["custom_id"])
        itens = loja._views.get(interacao.message.id if interacao.message else None, {})
        item = itens.get(chave) or loja._views.get(None, {}).get(chave)
        if item is None and any(p.fullmatch(chave[1]) for p in loja._dynamic_items):
            return False
        return item is None or item.view is None
    except Exception:
        return False


def instalar(bot: discord.Client):
    discord.InteractionResponse.send_message = _enviar
    discord.InteractionResponse.edit_message = _editar
    discord.InteractionResponse.defer = _adiar

    @bot.listen("on_interaction")
    async def _ao_receber(interacao: discord.Interaction):
        if interacao.type == discord.InteractionType.component and _botao_sem_dono(bot, interacao):
            try:
                await _enviar_original(interacao.response,
                                       "⌛ Esse jogo não está mais ativo (ele acabou ou o bot reiniciou). "
                                       "Comece outro com o comando!", ephemeral=True)
            except discord.HTTPException:
                pass
            return
        if interacao.type in (discord.InteractionType.application_command, discord.InteractionType.component):
            asyncio.create_task(_vigiar(interacao))
