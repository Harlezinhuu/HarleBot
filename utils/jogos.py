"""Regras dos jogos, separadas do Discord para poderem ser testadas."""
import random
import unicodedata
from typing import List, Optional

# ===================== Jogo da velha =====================

LINHAS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # horizontais
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # verticais
    (0, 4, 8), (2, 4, 6),             # diagonais
]


def vencedor_velha(tab: List[Optional[str]]) -> Optional[str]:
    """Devolve 'X', 'O', 'empate' ou None se o jogo ainda não acabou."""
    for a, b, c in LINHAS:
        if tab[a] and tab[a] == tab[b] == tab[c]:
            return tab[a]
    if all(tab):
        return "empate"
    return None


def _minimax(tab, vez, eu):
    fim = vencedor_velha(tab)
    if fim == eu:
        return 1
    if fim == "empate":
        return 0
    if fim:
        return -1
    outro = "O" if vez == "X" else "X"
    notas = []
    for i in range(9):
        if tab[i] is None:
            tab[i] = vez
            notas.append(_minimax(tab, outro, eu))
            tab[i] = None
    return max(notas) if vez == eu else min(notas)


def jogada_do_bot(tab: List[Optional[str]], simbolo: str, chance_de_errar: float = 0.25) -> int:
    """Escolhe a casa do bot. Com `chance_de_errar`, ele joga aleatório para dar chance de vencer."""
    livres = [i for i in range(9) if tab[i] is None]
    if random.random() < chance_de_errar:
        return random.choice(livres)
    outro = "O" if simbolo == "X" else "X"
    melhor, melhor_nota = livres[0], -2
    for i in livres:
        tab[i] = simbolo
        nota = _minimax(tab, outro, simbolo)
        tab[i] = None
        if nota > melhor_nota:
            melhor, melhor_nota = i, nota
    return melhor


# ===================== Forca =====================

DESENHOS = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n=========```",
]
MAX_ERROS = len(DESENHOS) - 1


def sem_acento(texto: str) -> str:
    """'Maracujá' -> 'maracuja'"""
    normal = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in normal if unicodedata.category(c) != "Mn")


class Forca:
    def __init__(self, palavra: str, dica: str):
        self.palavra = palavra.upper()
        self.dica = dica
        self.base = sem_acento(palavra)
        self.tentadas: List[str] = []
        self.erros = 0

    @property
    def mascara(self) -> str:
        saida = []
        for original, base in zip(self.palavra, self.base):
            if not base.isalpha() or base in self.tentadas:
                saida.append(original)
            else:
                saida.append("_")
        return " ".join(saida)

    @property
    def erradas(self) -> List[str]:
        return [letra for letra in self.tentadas if letra not in self.base]

    @property
    def ganhou(self) -> bool:
        return all(not c.isalpha() or c in self.tentadas for c in self.base)

    @property
    def perdeu(self) -> bool:
        return self.erros >= MAX_ERROS

    @property
    def acabou(self) -> bool:
        return self.ganhou or self.perdeu

    def chutar_letra(self, letra: str) -> str:
        """Devolve 'invalida', 'repetida', 'acerto' ou 'erro'."""
        letra = sem_acento(letra.strip())
        if len(letra) != 1 or not letra.isalpha():
            return "invalida"
        if letra in self.tentadas:
            return "repetida"
        self.tentadas.append(letra)
        if letra in self.base:
            return "acerto"
        self.erros = min(MAX_ERROS, self.erros + 1)
        return "erro"

    def chutar_palavra(self, chute: str) -> bool:
        """Acertou a palavra inteira? Errar custa 2 vidas."""
        if sem_acento(chute.strip()) == self.base:
            self.tentadas.extend(c for c in self.base if c.isalpha() and c not in self.tentadas)
            return True
        self.erros = min(MAX_ERROS, self.erros + 2)
        return False


# ===================== Pedra, papel e tesoura =====================

GANHA_DE = {"pedra": "tesoura", "papel": "pedra", "tesoura": "papel"}


def resultado_ppt(jogador: str, bot: str) -> str:
    """'vitoria', 'derrota' ou 'empate' do ponto de vista do jogador."""
    if jogador == bot:
        return "empate"
    return "vitoria" if GANHA_DE[jogador] == bot else "derrota"
