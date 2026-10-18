"""Nome e formato da moeda do bot. Mude aqui para renomear em todo lugar."""

import random

NOME = "Harlecoins"
APOSTA_MAXIMA = 10_000_000      # na prática sem limite (o Discord exige um número máximo)
sorteio = random.SystemRandom()  # sorteio usando a aleatoriedade do sistema operacional
EMOJI = "🪙"


def fmt(valor: int) -> str:
    """1500 -> '🪙 **1.500** Harlecoins'"""
    return f"{EMOJI} **{valor:,}** {NOME}".replace(",", ".")
