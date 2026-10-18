import random

from utils import truco_ia
from utils.truco import EMPATE, Carta, JogadaInvalida, Truco


def _jogo_com(maos, vira, n=2):
    j = Truco(n, random.Random(0))
    j.maos = {i: list(m) for i, m in enumerate(maos)}
    j.vira = vira
    from utils.truco import ORDEM
    j.manilha = ORDEM[(ORDEM.index(vira.valor) + 1) % len(ORDEM)]
    j.primeiro = j.vez = 0
    j.onze_pendente = None
    j.sem_truco = False
    return j


def test_forca_e_manilha():
    j = _jogo_com([[], []], Carta("7", "♣"))      # vira 7 -> manilha Q
    assert j.manilha == "Q"
    assert j.forca(Carta("Q", "♣")) > j.forca(Carta("Q", "♥")) > j.forca(Carta("Q", "♠")) > j.forca(Carta("Q", "♦"))
    assert j.forca(Carta("Q", "♦")) > j.forca(Carta("3", "♣"))   # manilha bate o 3
    assert j.forca(Carta("3", "♦")) > j.forca(Carta("2", "♣")) > j.forca(Carta("A", "♥")) > j.forca(Carta("K", "♠"))
    j2 = _jogo_com([[], []], Carta("3", "♦"))     # vira 3 -> manilha 4 (dá a volta)
    assert j2.manilha == "4"


def test_mao_ganha_com_duas_rodadas():
    c = Carta
    j = _jogo_com([[c("3", "♦"), c("2", "♦"), c("4", "♦")], [c("5", "♠"), c("6", "♠"), c("7", "♠")]], c("K", "♣"))
    j.jogar(0, 0); j.jogar(1, 0)        # 3 x 5 -> time 0
    assert j.rodadas == [0] and j.vez == 0
    j.jogar(0, 0); j.jogar(1, 0)        # 2 x 6 -> time 0 leva a mão
    assert j.pontos == [1, 0]


def test_primeira_empatada_decide_na_segunda():
    c = Carta
    j = _jogo_com([[c("3", "♦"), c("4", "♦"), c("5", "♦")], [c("3", "♠"), c("K", "♠"), c("6", "♠")]], c("7", "♣"))
    j.jogar(0, 0); j.jogar(1, 0)        # 3 x 3 -> empate
    assert j.rodadas == [EMPATE] and j.vez == 0
    j.jogar(0, 0); j.jogar(1, 0)        # 4 x K -> time 1 leva
    assert j.pontos == [0, 1]


def test_truco_correr_e_aumentar():
    c = Carta
    j = _jogo_com([[c("3", "♦"), c("2", "♦"), c("4", "♦")], [c("5", "♠"), c("6", "♠"), c("7", "♠")]], c("K", "♣"))
    j.pedir(0)
    assert j.proxima_acao() == ("resposta", 1)
    try:
        j.jogar(0, 0)
        raise AssertionError("não podia jogar com truco pendente")
    except JogadaInvalida:
        pass
    j.responder(1, "aumentar")          # seis!
    assert j.valor == 3 and j.pedido == {"time": 1, "valor": 6}
    j.responder(0, "correr")            # quem correu do seis entrega 3
    assert j.pontos == [0, 3]


def test_quem_aumentou_nao_pede_de_novo():
    c = Carta
    j = _jogo_com([[c("3", "♦"), c("2", "♦"), c("4", "♦")], [c("5", "♠"), c("6", "♠"), c("7", "♠")]], c("K", "♣"))
    j.pedir(0); j.responder(1, "aceitar")
    assert j.valor == 3 and not j.pode_pedir(0)
    j.jogar(0, 0)
    assert j.pode_pedir(1)              # o outro time pode pedir seis


def test_mao_de_onze():
    j = Truco(2, random.Random(5))
    j.pontos = [11, 4]
    j.nova_mao()
    assert j.proxima_acao() == ("onze", 0) and not j.pode_pedir(j.vez)
    j.decidir_onze(0, jogar=False)
    assert j.pontos == [11, 5]


def _partida_de_bots(n, semente):
    rng = random.Random(semente)
    j = Truco(n, rng)
    passos = 0
    while not j.acabou:
        passos += 1
        assert passos < 5000
        tipo, quem = j.proxima_acao()
        if tipo == "onze":
            j.decidir_onze(quem, truco_ia.decidir_onze(j, quem, rng))
        elif tipo == "resposta":
            j.responder(quem, truco_ia.responder(j, quem, rng))
        else:
            if truco_ia.quer_pedir(j, quem, rng):
                j.pedir(quem)
                continue
            j.jogar(quem, truco_ia.escolher_carta(j, quem, rng))
        assert all(0 <= p <= 12 for p in j.pontos)
        assert all(len(m) <= 3 for m in j.maos.values())
    return j


def test_milhares_de_partidas_terminam():
    vitorias = [0, 0]
    for semente in range(1500):
        j = _partida_de_bots(2 if semente % 2 else 4, semente)
        assert j.pontos[j.vencedor] == 12
        vitorias[j.vencedor] += 1
    assert min(vitorias) > 500           # nenhum lado ganha sempre
