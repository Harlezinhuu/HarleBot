"""Nome e formato da moeda do bot. Mude aqui para renomear em todo lugar."""

import random

NOME = "Harlecoins"
APOSTA_MAXIMA = 50_000          # limite por aposta, para a economia não explodir
sorteio = random.SystemRandom()  # sorteio usando a aleatoriedade do sistema operacional
EMOJI = "🪙"


def fmt(valor: int) -> str:
    """1500 -> '🪙 **1.500** Harlecoins'"""
    return f"{EMOJI} **{valor:,}** {NOME}".replace(",", ".")
