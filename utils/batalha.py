"""Regras da batalha 1x1 (sem Discord, para poder testar)."""
import random
from typing import Dict, List, Optional

VIDA_MAXIMA = 100
CURAS_POR_PESSOA = 2


class Lutador:
    def __init__(self, uid: int, nome: str):
        self.uid = uid
        self.nome = nome
        self.vida = VIDA_MAXIMA
        self.defendendo = False
        self.curas = CURAS_POR_PESSOA
        self.especial_pronto = True


class Batalha:
    def __init__(self, a: Lutador, b: Lutador, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.lutadores: List[Lutador] = [a, b]
        self.vez = self.rng.randint(0, 1)
        self.historico: List[str] = []
        self.vencedor: Optional[Lutador] = None
        self.turno = 1

    @property
    def atual(self) -> Lutador:
        return self.lutadores[self.vez]

    @property
    def alvo(self) -> Lutador:
        return self.lutadores[1 - self.vez]

    @property
    def acabou(self) -> bool:
        return self.vencedor is not None

    def _dano(self, minimo: int, maximo: int, chance_de_errar: float, chance_critico: float) -> str:
        eu, ele = self.atual, self.alvo
        if self.rng.random() < chance_de_errar:
            return f"{eu.nome} errou o golpe!"
        dano = self.rng.randint(minimo, maximo)
        extra = ""
        if self.rng.random() < chance_critico:
            dano *= 2
            extra = " **CRÍTICO!**"
        if ele.defendendo:
            dano //= 2
            extra += " (defendido pela metade)"
            ele.defendendo = False
        ele.vida = max(0, ele.vida - dano)
        return f"{eu.nome} causou **{dano}** de dano em {ele.nome}.{extra}"

    def agir(self, acao: str) -> str:
        """Executa a ação da pessoa da vez: 'atacar', 'especial', 'defender' ou 'curar'."""
        if self.acabou:
            return "A batalha já acabou."
        eu = self.atual

        if acao == "atacar":
            texto = "⚔️ " + self._dano(10, 22, chance_de_errar=0.10, chance_critico=0.15)
        elif acao == "especial":
            if not eu.especial_pronto:
                return "O especial ainda está carregando."
            eu.especial_pronto = False
            texto = "💥 " + self._dano(25, 40, chance_de_errar=0.35, chance_critico=0.0)
        elif acao == "defender":
            eu.defendendo = True
            eu.especial_pronto = True  # defender recarrega o especial
            texto = f"🛡️ {eu.nome} se defendeu e recarregou o especial."
        elif acao == "curar":
            if eu.curas <= 0:
                return "Acabaram as curas."
            eu.curas -= 1
            cura = self.rng.randint(15, 25)
            eu.vida = min(VIDA_MAXIMA, eu.vida + cura)
            texto = f"🧪 {eu.nome} recuperou **{cura}** de vida."
        else:
            return "Ação inválida."

        self.historico.append(texto)
        if self.alvo.vida <= 0:
            self.vencedor = eu
        else:
            self.vez = 1 - self.vez
            self.turno += 1
        return texto

    def desistencia(self, uid: int):
        """Quem desistiu (ou demorou demais) perde."""
        perdedor = next(l for l in self.lutadores if l.uid == uid)
        self.vencedor = next(l for l in self.lutadores if l is not perdedor)
