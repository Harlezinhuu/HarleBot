"""Regras do blackjack e do campo minado (sem Discord, para poder testar)."""
import random
from typing import List, Optional, Tuple

# ============================== BLACKJACK ==============================

NAIPES = ["♠", "♥", "♦", "♣"]
VALORES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
Carta = Tuple[str, str]


def novo_baralho(rng: Optional[random.Random] = None) -> List[Carta]:
    baralho = [(v, n) for n in NAIPES for v in VALORES]
    (rng or random).shuffle(baralho)
    return baralho


def valor_mao(cartas: List[Carta]) -> int:
    """Soma da mão. Ás vale 11, ou 1 se 11 estourar."""
    total, ases = 0, 0
    for valor, _ in cartas:
        if valor == "A":
            total += 11
            ases += 1
        elif valor in ("J", "Q", "K"):
            total += 10
        else:
            total += int(valor)
    while total > 21 and ases:
        total -= 10
        ases -= 1
    return total


def mostrar(cartas: List[Carta], esconder_segunda: bool = False) -> str:
    textos = [f"`{v}{n}`" for v, n in cartas]
    if esconder_segunda and len(textos) > 1:
        textos[1] = "`??`"
    return " ".join(textos)


class Blackjack:
    def __init__(self, aposta: int, rng: Optional[random.Random] = None):
        self.aposta = aposta
        self.baralho = novo_baralho(rng)
        self.jogador = [self.baralho.pop(), self.baralho.pop()]
        self.mesa = [self.baralho.pop(), self.baralho.pop()]
        self.resultado: Optional[str] = None  # 'blackjack', 'vitoria', 'empate', 'derrota', 'estourou'
        self.dobrou = False
        # Blackjack de cara (de qualquer um dos lados) encerra na hora
        if valor_mao(self.jogador) == 21 or valor_mao(self.mesa) == 21:
            self._finalizar()

    @property
    def acabou(self) -> bool:
        return self.resultado is not None

    @property
    def pode_dobrar(self) -> bool:
        return not self.acabou and len(self.jogador) == 2 and not self.dobrou

    def pedir(self):
        self.jogador.append(self.baralho.pop())
        if valor_mao(self.jogador) > 21:
            self.resultado = "estourou"
        elif valor_mao(self.jogador) == 21:
            self.parar()

    def dobrar(self):
        self.dobrou = True
        self.aposta *= 2
        self.jogador.append(self.baralho.pop())
        if valor_mao(self.jogador) > 21:
            self.resultado = "estourou"
        else:
            self.parar()

    def parar(self):
        # A mesa compra até ter 17 ou mais
        while valor_mao(self.mesa) < 17:
            self.mesa.append(self.baralho.pop())
        self._finalizar()

    def _finalizar(self):
        eu, mesa = valor_mao(self.jogador), valor_mao(self.mesa)
        natural_jogador = eu == 21 and len(self.jogador) == 2
        natural_mesa = mesa == 21 and len(self.mesa) == 2
        if natural_jogador and not natural_mesa:
            self.resultado = "blackjack"
        elif natural_jogador and natural_mesa:
            self.resultado = "empate"
        elif mesa > 21 or eu > mesa:
            self.resultado = "vitoria"
        elif eu == mesa:
            self.resultado = "empate"
        else:
            self.resultado = "derrota"

    @property
    def pagamento(self) -> int:
        """Quanto devolver ao jogador no fim (a aposta já foi descontada no começo)."""
        return {
            "blackjack": self.aposta + self.aposta * 3 // 2,  # paga 3 para 2
            "vitoria": self.aposta * 2,
            "empate": self.aposta,
        }.get(self.resultado, 0)


# ============================ CAMPO MINADO ============================

CASAS_MINAS = 20          # tabuleiro 4 x 5
MARGEM_DA_CASA = 0.97     # 3% de vantagem da casa, como nos jogos de verdade


def multiplicador_minas(bombas: int, abertas: int) -> float:
    """Multiplicador justo depois de abrir `abertas` casas seguras."""
    mult = MARGEM_DA_CASA
    for i in range(abertas):
        mult *= (CASAS_MINAS - i) / (CASAS_MINAS - bombas - i)
    return round(mult, 2) if abertas else 1.0


class Minas:
    def __init__(self, aposta: int, bombas: int, rng: Optional[random.Random] = None):
        self.aposta = aposta
        self.bombas = set((rng or random).sample(range(CASAS_MINAS), bombas))
        self.abertas: List[int] = []
        self.explodiu: Optional[int] = None
        self.sacou = False

    @property
    def seguras_restantes(self) -> int:
        return CASAS_MINAS - len(self.bombas) - len(self.abertas)

    @property
    def multiplicador(self) -> float:
        return multiplicador_minas(len(self.bombas), len(self.abertas))

    @property
    def premio_atual(self) -> int:
        return int(self.aposta * self.multiplicador) if self.abertas else self.aposta

    @property
    def proximo_premio(self) -> int:
        return int(self.aposta * multiplicador_minas(len(self.bombas), len(self.abertas) + 1))

    @property
    def acabou(self) -> bool:
        return self.explodiu is not None or self.sacou

    def abrir(self, casa: int) -> str:
        """Devolve 'bomba', 'diamante', 'limpou' (abriu todas as seguras) ou 'ja_aberta'."""
        if casa in self.abertas or self.acabou:
            return "ja_aberta"
        if casa in self.bombas:
            self.explodiu = casa
            return "bomba"
        self.abertas.append(casa)
        if self.seguras_restantes == 0:
            self.sacou = True
            return "limpou"
        return "diamante"

    def sacar(self) -> int:
        """Encerra e devolve quanto a pessoa recebe."""
        self.sacou = True
        return self.premio_atual
