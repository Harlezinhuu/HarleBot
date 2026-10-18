"""Regras do Truco Paulista (sem Discord, para poder testar).

- Baralho de 40 cartas (sem 8, 9 e 10).
- Força normal: 4 < 5 < 6 < 7 < Q < J < K < A < 2 < 3.
- Manilha: a carta seguinte à "vira". Entre manilhas: ♦ ouros < ♠ espadas < ♥ copas < ♣ paus (zap).
- Cada mão tem até 3 rodadas; quem ganhar 2 leva. Partida até 12 pontos.
- Truco (3), seis (6), nove (9), doze (12). Quem corre entrega o valor que já estava valendo.
- Mão de onze: o time com 11 vê as cartas e decide se joga (vale 3) ou corre (o outro ganha 1).
  Na mão de onze e na mão de ferro (11 a 11) não pode pedir truco.
"""
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ORDEM = ["4", "5", "6", "7", "Q", "J", "K", "A", "2", "3"]
NAIPES = ["♦", "♠", "♥", "♣"]
PROXIMO_VALOR = {1: 3, 3: 6, 6: 9, 9: 12}
NOME_PEDIDO = {3: "Truco", 6: "Seis", 9: "Nove", 12: "Doze"}
PONTOS_PARA_VENCER = 12
EMPATE = -1


@dataclass(frozen=True)
class Carta:
    valor: str
    naipe: str

    def __str__(self):
        return f"{self.valor}{self.naipe}"


class JogadaInvalida(Exception):
    pass


class Truco:
    def __init__(self, num_jogadores: int, rng: Optional[random.Random] = None):
        if num_jogadores not in (2, 4):
            raise ValueError("truco é 1x1 ou 2x2")
        self.n = num_jogadores
        self.rng = rng or random.Random()
        self.pontos = [0, 0]
        self.dealer = self.rng.randrange(self.n)
        self.vencedor: Optional[int] = None
        self.log: List[str] = []
        self.nomes = [f"Jogador {i + 1}" for i in range(self.n)]
        self.nova_mao()

    # ---------------- utilidades ----------------

    @staticmethod
    def time_de(idx: int) -> int:
        return idx % 2

    def nome_time(self, time: int) -> str:
        membros = [self.nomes[i] for i in range(self.n) if i % 2 == time]
        return " e ".join(membros)

    def forca(self, carta: Carta) -> int:
        if carta.valor == self.manilha:
            return 10 + NAIPES.index(carta.naipe)
        return ORDEM.index(carta.valor)

    def eh_manilha(self, carta: Carta) -> bool:
        return carta.valor == self.manilha

    @property
    def acabou(self) -> bool:
        return self.vencedor is not None

    # ---------------- começo de mão ----------------

    def nova_mao(self):
        baralho = [Carta(v, n) for v in ORDEM for n in NAIPES]
        self.rng.shuffle(baralho)
        self.dealer = (self.dealer + 1) % self.n
        self.maos: Dict[int, List[Carta]] = {i: [baralho.pop() for _ in range(3)] for i in range(self.n)}
        self.vira = baralho.pop()
        self.manilha = ORDEM[(ORDEM.index(self.vira.valor) + 1) % len(ORDEM)]
        self.primeiro = (self.dealer + 1) % self.n
        self.vez = self.primeiro
        self.mesa: List[Tuple[int, Carta]] = []
        self.rodadas: List[int] = []           # time que ganhou cada rodada, ou EMPATE
        self.ultima_mesa: List[Tuple[int, Carta]] = []
        self.valor = 1
        self.pedido: Optional[Dict] = None     # {"time": quem pediu, "valor": valor proposto}
        self.ultimo_a_aumentar: Optional[int] = None
        self.onze_pendente: Optional[int] = None
        self.sem_truco = False

        com_onze = [t for t in (0, 1) if self.pontos[t] == PONTOS_PARA_VENCER - 1]
        if len(com_onze) == 2:
            self.sem_truco = True
            self.log.append("🔥 Mão de ferro (11 a 11): vale 1 ponto e não tem truco.")
        elif len(com_onze) == 1:
            self.onze_pendente = com_onze[0]
            self.sem_truco = True
            self.log.append(f"✋ Mão de onze para {self.nome_time(com_onze[0])}: jogar ou correr?")

    # ---------------- quem precisa agir ----------------

    def proxima_acao(self) -> Tuple[str, int]:
        """('onze', time) | ('resposta', time) | ('carta', jogador) | ('fim', time_vencedor)"""
        if self.acabou:
            return "fim", self.vencedor
        if self.onze_pendente is not None:
            return "onze", self.onze_pendente
        if self.pedido:
            return "resposta", 1 - self.pedido["time"]
        return "carta", self.vez

    def pode_pedir(self, idx: int) -> bool:
        return (not self.acabou and self.onze_pendente is None and self.pedido is None and not self.sem_truco
                and self.vez == idx and self.valor < 12 and self.ultimo_a_aumentar != self.time_de(idx))

    def proximo_pedido(self) -> int:
        return PROXIMO_VALOR[self.valor]

    # ---------------- ações ----------------

    def decidir_onze(self, time: int, jogar: bool):
        if self.onze_pendente != time:
            raise JogadaInvalida("Não é hora de decidir a mão de onze.")
        self.onze_pendente = None
        if jogar:
            self.valor = 3
            self.log.append(f"✅ {self.nome_time(time)} vai jogar a mão de onze (vale 3).")
        else:
            self.log.append(f"🏃 {self.nome_time(time)} correu da mão de onze.")
            self._pontuar(1 - time, 1)

    def pedir(self, idx: int):
        if not self.pode_pedir(idx):
            raise JogadaInvalida("Você não pode pedir agora.")
        proposto = self.proximo_pedido()
        self.pedido = {"time": self.time_de(idx), "valor": proposto}
        self.log.append(f"🗣️ {self.nomes[idx]} pediu **{NOME_PEDIDO[proposto].upper()}!**")

    def responder(self, time: int, acao: str):
        if not self.pedido or self.pedido["time"] == time:
            raise JogadaInvalida("Não tem pedido para você responder.")
        pediu, proposto = self.pedido["time"], self.pedido["valor"]
        if acao == "aceitar":
            self.valor = proposto
            self.ultimo_a_aumentar = pediu
            self.pedido = None
            self.log.append(f"👍 {self.nome_time(time)} aceitou. A mão vale **{proposto}**.")
        elif acao == "correr":
            self.pedido = None
            self.log.append(f"🏃 {self.nome_time(time)} correu.")
            self._pontuar(pediu, self.valor)
        elif acao == "aumentar":
            if proposto >= 12:
                raise JogadaInvalida("Não dá para aumentar mais que doze.")
            self.valor = proposto
            novo = PROXIMO_VALOR[proposto]
            self.pedido = {"time": time, "valor": novo}
            self.ultimo_a_aumentar = pediu
            self.log.append(f"🔥 {self.nome_time(time)} aumentou: **{NOME_PEDIDO[novo].upper()}!**")
        else:
            raise JogadaInvalida("Resposta inválida.")

    def jogar(self, idx: int, posicao: int):
        if self.acabou or self.onze_pendente is not None or self.pedido:
            raise JogadaInvalida("Espere a decisão pendente.")
        if self.vez != idx:
            raise JogadaInvalida("Não é a sua vez.")
        mao = self.maos[idx]
        if not 0 <= posicao < len(mao):
            raise JogadaInvalida("Carta inválida.")
        carta = mao.pop(posicao)
        self.mesa.append((idx, carta))
        self.log.append(f"🃏 {self.nomes[idx]} jogou **{carta}**")
        self.vez = (idx + 1) % self.n
        if len(self.mesa) == self.n:
            self._fechar_rodada()

    # ---------------- regras internas ----------------

    def _fechar_rodada(self):
        maior = max(self.forca(c) for _, c in self.mesa)
        vencedores = [i for i, c in self.mesa if self.forca(c) == maior]
        times = {self.time_de(i) for i in vencedores}
        if len(times) == 1:
            resultado = times.pop()
            self.vez = vencedores[0]
            self.log.append(f"✔️ Rodada {len(self.rodadas) + 1}: {self.nome_time(resultado)}")
        else:
            resultado = EMPATE
            self.vez = self.mesa[0][0]
            self.log.append(f"➖ Rodada {len(self.rodadas) + 1}: empatou (cangou)")
        self.rodadas.append(resultado)
        self.ultima_mesa = self.mesa
        self.mesa = []

        ganhou = self._vencedor_da_mao()
        if ganhou is not None:
            if ganhou == EMPATE:
                self.log.append("🤝 As três rodadas empataram: ninguém pontua.")
                self._proxima_mao()
            else:
                self._pontuar(ganhou, self.valor)

    def _vencedor_da_mao(self) -> Optional[int]:
        """Time que levou a mão, EMPATE (ninguém pontua) ou None (continua)."""
        r = self.rodadas
        if len(r) == 2:
            a, b = r
            if a != EMPATE and a == b:
                return a
            if a == EMPATE and b != EMPATE:
                return b
            if a != EMPATE and b == EMPATE:
                return a
            return None
        if len(r) == 3:
            a, b, c = r
            if c != EMPATE:
                return c
            if a != EMPATE:
                return a
            if b != EMPATE:
                return b
            return EMPATE
        return None

    def _pontuar(self, time: int, pontos: int):
        self.pontos[time] = min(PONTOS_PARA_VENCER, self.pontos[time] + pontos)
        self.log.append(f"⭐ {self.nome_time(time)} {'ganharam' if self.n == 4 else 'ganhou'} **{pontos}** "
                        f"{'ponto' if pontos == 1 else 'pontos'}. Placar: {self.pontos[0]} x {self.pontos[1]}")
        if self.pontos[time] >= PONTOS_PARA_VENCER:
            self.vencedor = time
            verbo = "venceram" if self.n == 4 else "venceu"
            self.log.append(f"🏆 {self.nome_time(time)} {verbo} a partida!")
        else:
            self._proxima_mao()

    def _proxima_mao(self):
        self.nova_mao()

    def desistir(self, time: int):
        """O time perde a partida (desistência ou demora)."""
        self.vencedor = 1 - time
        self.log.append(f"🏳️ {self.nome_time(time)} perdeu por desistência.")
