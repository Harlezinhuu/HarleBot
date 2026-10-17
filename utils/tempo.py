"""Converte textos como "10m", "1h30m" ou "2d" em tempo."""
import re
from datetime import timedelta
from typing import Optional

_UNIDADES = {"s": 1, "m": 60, "min": 60, "h": 3600, "d": 86400, "w": 604800, "sem": 604800}
_PADRAO = re.compile(r"(\d+)(sem|min|s|m|h|d|w)")


def converter(texto: str) -> Optional[timedelta]:
    """'1h30m' -> 1 hora e 30 minutos. Devolve None se o texto não for um tempo válido."""
    texto = (texto or "").strip().lower().replace(" ", "")
    if not texto:
        return None
    total, posicao = 0, 0
    for m in _PADRAO.finditer(texto):
        if m.start() != posicao:
            return None
        total += int(m.group(1)) * _UNIDADES[m.group(2)]
        posicao = m.end()
    if posicao != len(texto) or total <= 0:
        return None
    return timedelta(seconds=total)


def formatar(tempo: timedelta) -> str:
    """timedelta(hours=1, minutes=30) -> '1 hora e 30 minutos'."""
    segundos = int(tempo.total_seconds())
    partes = []
    for singular, plural, tamanho in (
        ("dia", "dias", 86400),
        ("hora", "horas", 3600),
        ("minuto", "minutos", 60),
        ("segundo", "segundos", 1),
    ):
        qtd, segundos = divmod(segundos, tamanho)
        if qtd:
            partes.append(f"{qtd} {singular if qtd == 1 else plural}")
    if not partes:
        return "0 segundos"
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " e " + partes[-1]
