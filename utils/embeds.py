"""Mensagens bonitas (embeds) com as cores do Harle."""
from datetime import datetime, timezone
from typing import Dict, Optional

import discord

AZUL = 0x4C8DFF
VERDE = 0x3CC88B
VERMELHO = 0xE5484D
AMBAR = 0xF2A93B
CINZA = 0x6F7682

# ação -> (nome, cor, emoji)
ACOES = {
    "ban": ("Banimento", VERMELHO, "🔨"),
    "unban": ("Desbanimento", VERDE, "🔓"),
    "kick": ("Expulsão", AMBAR, "👢"),
    "timeout": ("Silenciamento", AMBAR, "🔇"),
    "untimeout": ("Fim do silenciamento", VERDE, "🔊"),
    "warn": ("Aviso", AMBAR, "⚠️"),
}


def agora():
    return datetime.now(timezone.utc)


def cortar(texto: str, limite: int = 1000) -> str:
    texto = texto or ""
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def sucesso(texto: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {texto}", color=VERDE)


def erro(texto: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {texto}", color=VERMELHO)


def caso(acao: str, alvo: discord.abc.User, moderador: discord.abc.User, motivo: Optional[str],
         numero: int, extra: Optional[Dict[str, str]] = None) -> discord.Embed:
    nome, cor, emoji = ACOES[acao]
    e = discord.Embed(title=f"{emoji} {nome} · Caso #{numero}", color=cor, timestamp=agora())
    e.add_field(name="Usuário", value=f"{alvo.mention}\n`{alvo}` ({alvo.id})")
    e.add_field(name="Moderador", value=moderador.mention)
    for nome_campo, valor in (extra or {}).items():
        e.add_field(name=nome_campo, value=valor)
    e.add_field(name="Motivo", value=cortar(motivo or "Sem motivo informado", 1024), inline=False)
    e.set_thumbnail(url=alvo.display_avatar.url)
    return e
