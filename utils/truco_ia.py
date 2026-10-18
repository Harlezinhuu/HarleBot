"""Cérebro do bot no truco: regras simples, mas que jogam de um jeito razoável e às vezes blefam."""
import random
from typing import List, Optional

from utils.truco import EMPATE, PROXIMO_VALOR, Truco


def _forcas(jogo: Truco, idx: int) -> List[int]:
    return sorted(jogo.forca(c) for c in jogo.maos[idx])


def poder_da_mao(jogo: Truco, idx: int) -> float:
    """0 a ~3: quanto a mão é boa. Manilha vale muito; A, 2 e 3 valem um pouco."""
    poder = 0.0
    for f in _forcas(jogo, idx):
        if f >= 10:
            poder += 1.0 + (f - 10) * 0.15
        elif f >= 7:
            poder += 0.35 + (f - 7) * 0.1
    rodadas_minhas = sum(1 for r in jogo.rodadas if r == jogo.time_de(idx))
    rodadas_deles = sum(1 for r in jogo.rodadas if r not in (EMPATE, jogo.time_de(idx)))
    return poder + 0.6 * rodadas_minhas - 0.6 * rodadas_deles


def escolher_carta(jogo: Truco, idx: int, rng: Optional[random.Random] = None) -> int:
    rng = rng or random
    mao = jogo.maos[idx]
    ordem = sorted(range(len(mao)), key=lambda i: jogo.forca(mao[i]))  # posições da mais fraca à mais forte
    if not jogo.mesa:
        if len(mao) == 3:
            return ordem[1]          # abre a primeira rodada com a do meio
        return ordem[-1]             # depois, vai com a mais forte
    maior = max(jogo.forca(c) for _, c in jogo.mesa)
    dono = next(i for i, c in jogo.mesa if jogo.forca(c) == maior)
    if jogo.time_de(dono) == jogo.time_de(idx):
        return ordem[0]              # o parceiro já está ganhando: joga a mais fraca
    for pos in ordem:
        if jogo.forca(mao[pos]) > maior:
            return pos               # a mais fraca que ganha
    return ordem[0]                  # não dá para ganhar: descarta a mais fraca


def quer_pedir(jogo: Truco, idx: int, rng: Optional[random.Random] = None) -> bool:
    rng = rng or random
    if not jogo.pode_pedir(idx):
        return False
    poder = poder_da_mao(jogo, idx)
    if poder >= 1.6:
        return rng.random() < 0.75
    if poder >= 1.0:
        return rng.random() < 0.3
    return rng.random() < 0.06       # blefe de vez em quando


def responder(jogo: Truco, time: int, rng: Optional[random.Random] = None) -> str:
    rng = rng or random
    membros = [i for i in range(jogo.n) if jogo.time_de(i) == time]
    poder = max(poder_da_mao(jogo, i) for i in membros)
    proposto = jogo.pedido["valor"]
    exigencia = {3: 0.7, 6: 1.1, 9: 1.5, 12: 1.9}[proposto]
    if poder >= exigencia + 0.8 and proposto in PROXIMO_VALOR and rng.random() < 0.45:
        return "aumentar"
    if poder >= exigencia or rng.random() < 0.12:
        return "aceitar"
    return "correr"


def decidir_onze(jogo: Truco, time: int, rng: Optional[random.Random] = None) -> bool:
    membros = [i for i in range(jogo.n) if jogo.time_de(i) == time]
    return max(poder_da_mao(jogo, i) for i in membros) >= 0.9
