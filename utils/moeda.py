"""Nome e formato da moeda do bot. Mude aqui para renomear em todo lugar."""

NOME = "Harlecoins"
EMOJI = "🪙"


def fmt(valor: int) -> str:
    """1500 -> '🪙 **1.500** Harlecoins'"""
    return f"{EMOJI} **{valor:,}** {NOME}".replace(",", ".")
