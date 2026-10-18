"""Regras do automod e do anti-raid (sem Discord, para poder testar)."""
import re
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from utils.jogos import sem_acento

LINK = re.compile(r"(https?://|www\.)\S+", re.I)
CONVITE = re.compile(r"(discord\.gg|discord(app)?\.com/invite|dsc\.gg)/\S+", re.I)


def tem_link(texto: str) -> bool:
    return bool(LINK.search(texto))


def tem_convite(texto: str) -> bool:
    return bool(CONVITE.search(texto))


def excesso_de_maiusculas(texto: str, minimo_letras: int = 12, limite: float = 0.7) -> bool:
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < minimo_letras:
        return False
    return sum(c.isupper() for c in letras) / len(letras) >= limite


def palavra_proibida(texto: str, proibidas: Iterable[str]) -> Optional[str]:
    """Devolve a palavra proibida encontrada (ignora acentos e maiúsculas), ou None."""
    normal = f" {re.sub(r'[^a-z0-9]+', ' ', sem_acento(texto))} "
    for palavra in proibidas:
        alvo = re.sub(r"[^a-z0-9]+", " ", sem_acento(palavra)).strip()
        if alvo and f" {alvo} " in normal:
            return palavra
    return None


class DetectorDeSpam:
    """Spam = muitas mensagens em poucos segundos, ou a mesma mensagem repetida várias vezes."""

    def __init__(self, maximo: int = 6, janela: float = 7.0, repeticoes: int = 3):
        self.maximo, self.janela, self.repeticoes = maximo, janela, repeticoes
        self._horarios: Dict[Tuple[int, int], Deque[float]] = defaultdict(deque)
        self._ultimas: Dict[Tuple[int, int], Deque[str]] = defaultdict(lambda: deque(maxlen=self.repeticoes))

    def registrar(self, guild_id: int, user_id: int, texto: str, agora: Optional[float] = None) -> bool:
        agora = time.monotonic() if agora is None else agora
        chave = (guild_id, user_id)
        horarios = self._horarios[chave]
        horarios.append(agora)
        while horarios and agora - horarios[0] > self.janela:
            horarios.popleft()
        ultimas = self._ultimas[chave]
        texto_normal = texto.strip().lower()
        if texto_normal:
            ultimas.append(texto_normal)
        repetiu = len(ultimas) == self.repeticoes and len(set(ultimas)) == 1
        if len(horarios) > self.maximo or repetiu:
            horarios.clear()
            ultimas.clear()
            return True
        return False


class ContadorDeInfracoes:
    """Conta infrações por pessoa numa janela de tempo (para punir quem insiste)."""

    def __init__(self, janela: float = 600.0):
        self.janela = janela
        self._registros: Dict[Tuple[int, int], Deque[float]] = defaultdict(deque)

    def somar(self, guild_id: int, user_id: int, agora: Optional[float] = None) -> int:
        agora = time.monotonic() if agora is None else agora
        fila = self._registros[(guild_id, user_id)]
        fila.append(agora)
        while fila and agora - fila[0] > self.janela:
            fila.popleft()
        return len(fila)

    def zerar(self, guild_id: int, user_id: int):
        self._registros.pop((guild_id, user_id), None)


class DetectorDeRaid:
    """Raid = muitas entradas no servidor em pouco tempo."""

    def __init__(self):
        self._entradas: Dict[int, Deque[float]] = defaultdict(deque)

    def registrar(self, guild_id: int, limite: int, janela: float, agora: Optional[float] = None) -> bool:
        agora = time.monotonic() if agora is None else agora
        fila = self._entradas[guild_id]
        fila.append(agora)
        while fila and agora - fila[0] > janela:
            fila.popleft()
        return len(fila) >= limite

    def limpar(self, guild_id: int):
        self._entradas.pop(guild_id, None)


def analisar_mensagem(texto: str, mencoes: int, config: Dict, proibidas: List[str]) -> Optional[str]:
    """Devolve o motivo da infração (texto curto) ou None se a mensagem está ok."""
    if config.get("anti_convites") and tem_convite(texto):
        return "convite de outro servidor"
    if config.get("anti_links") and tem_link(texto) and not tem_convite(texto):
        return "link"
    if config.get("anti_mencoes") and mencoes >= config.get("limite_mencoes", 5):
        return "excesso de menções"
    if config.get("anti_caps") and excesso_de_maiusculas(texto):
        return "excesso de letras maiúsculas"
    achada = palavra_proibida(texto, proibidas)
    if achada:
        return "palavra proibida"
    return None
