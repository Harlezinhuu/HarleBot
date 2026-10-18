"""Mensagens que o bot consegue editar por quanto tempo precisar.

A mensagem devolvida por `interaction.original_response()` é editada pelo "token" da interação,
que o Discord invalida depois de 15 minutos. Em jogos longos (xadrez, truco), as edições começavam
a falhar em silêncio e os botões paravam de funcionar. Aqui trocamos por uma referência pelo canal,
que usa o token do próprio bot e não expira.
"""
import discord


async def mensagem_duravel(interaction: discord.Interaction):
    original = await interaction.original_response()
    canal = interaction.channel
    if canal is not None and hasattr(canal, "get_partial_message"):
        return canal.get_partial_message(original.id)
    return original
