"""Contas de XP e nível."""
from typing import Tuple


def xp_para_subir(nivel: int) -> int:
    """XP necessário para ir do `nivel` para o próximo. Fica mais difícil a cada nível."""
    return 5 * nivel * nivel + 50 * nivel + 100


def nivel_de(xp_total: int) -> Tuple[int, int, int]:
    """Converte XP total em (nível, XP dentro do nível atual, XP necessário para o próximo)."""
    nivel = 0
    restante = max(xp_total, 0)
    while restante >= xp_para_subir(nivel):
        restante -= xp_para_subir(nivel)
        nivel += 1
    return nivel, restante, xp_para_subir(nivel)


def barra(atual: int, total: int, tamanho: int = 12) -> str:
    """Barra de progresso em texto: ▰▰▰▰▱▱▱▱"""
    cheio = 0 if total <= 0 else min(tamanho, round(tamanho * atual / total))
    return "▰" * cheio + "▱" * (tamanho - cheio)
