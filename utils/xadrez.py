"""Xadrez: desenho do tabuleiro, notação em português e o "cérebro" do bot.

As regras (roque, en passant, promoção, xeque-mate, empates) vêm da biblioteca python-chess.
"""
import io
import random
import time
from pathlib import Path
from typing import List, Optional

import chess
from PIL import Image, ImageDraw, ImageFont

# ============================== NOMES ==============================

NOME_PECA = {chess.PAWN: "Peão", chess.KNIGHT: "Cavalo", chess.BISHOP: "Bispo",
             chess.ROOK: "Torre", chess.QUEEN: "Dama", chess.KING: "Rei"}
LETRA_PT = {chess.KNIGHT: "C", chess.BISHOP: "B", chess.ROOK: "T", chess.QUEEN: "D", chess.KING: "R"}
PT_PARA_EN = {"C": "N", "B": "B", "T": "R", "D": "Q", "R": "K"}


def lance_em_portugues(tabuleiro: chess.Board, lance: chess.Move) -> str:
    """'Nf3' -> 'Cf3', 'Qxd8+' -> 'Dxd8+', 'e8=Q' -> 'e8=D'."""
    san = tabuleiro.san(lance)
    traducao = {"N": "C", "Q": "D", "R": "T", "K": "R"}
    return "".join(traducao.get(c, c) if c.isupper() else c for c in san)


def ler_lance(tabuleiro: chess.Board, texto: str) -> Optional[chess.Move]:
    """Entende 'Cf3' (português), 'Nf3' (inglês), 'e2e4' (UCI) e 'O-O'. Devolve None se não for válido."""
    texto = texto.strip().replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    if not texto:
        return None
    tentativas = []
    if texto[0] in PT_PARA_EN:
        tentativas.append(PT_PARA_EN[texto[0]] + texto[1:])
    convertido = texto
    if "=" in convertido and convertido[-1].upper() in PT_PARA_EN:
        convertido = convertido[:-1] + PT_PARA_EN[convertido[-1].upper()]
        tentativas.append(convertido)
    tentativas.append(texto)
    for tentativa in tentativas:
        try:
            return tabuleiro.parse_san(tentativa)
        except ValueError:
            pass
    try:
        lance = chess.Move.from_uci(texto.lower())
        return lance if lance in tabuleiro.legal_moves else None
    except ValueError:
        return None


# ============================== DESENHO ==============================

FONTE = Path(__file__).resolve().parent.parent / "assets" / "fontes" / "DejaVuSans.ttf"
CASA = 64
MARGEM = 26
CLARA, ESCURA = (235, 236, 208), (119, 149, 86)
ULTIMO_CLARO, ULTIMO_ESCURO = (246, 246, 130), (186, 202, 68)
XEQUE = (231, 76, 60)
FUNDO = (22, 24, 29)
SIMBOLO = {chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜", chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"}

_fontes = {}


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    if tamanho not in _fontes:
        try:
            _fontes[tamanho] = ImageFont.truetype(str(FONTE), tamanho)
        except OSError:
            _fontes[tamanho] = ImageFont.load_default()
    return _fontes[tamanho]


def desenhar(tabuleiro: chess.Board, de_baixo: chess.Color = chess.WHITE) -> io.BytesIO:
    """Desenha o tabuleiro em PNG. `de_baixo` é a cor que fica na parte de baixo."""
    lado = CASA * 8 + MARGEM * 2
    img = Image.new("RGB", (lado, lado), FUNDO)
    d = ImageDraw.Draw(img)
    ultimo = tabuleiro.peek() if tabuleiro.move_stack else None
    rei_em_xeque = tabuleiro.king(tabuleiro.turn) if tabuleiro.is_check() else None
    fonte_peca, fonte_coord = _fonte(int(CASA * 0.82)), _fonte(14)

    for linha in range(8):
        for coluna in range(8):
            if de_baixo == chess.WHITE:
                casa = chess.square(coluna, 7 - linha)
            else:
                casa = chess.square(7 - coluna, linha)
            x, y = MARGEM + coluna * CASA, MARGEM + linha * CASA
            clara = (chess.square_file(casa) + chess.square_rank(casa)) % 2 == 1
            cor = CLARA if clara else ESCURA
            if ultimo and casa in (ultimo.from_square, ultimo.to_square):
                cor = ULTIMO_CLARO if clara else ULTIMO_ESCURO
            d.rectangle([x, y, x + CASA - 1, y + CASA - 1], fill=cor)
            if casa == rei_em_xeque:
                d.ellipse([x + 4, y + 4, x + CASA - 5, y + CASA - 5], fill=XEQUE)

            peca = tabuleiro.piece_at(casa)
            if peca:
                branca = peca.color == chess.WHITE
                d.text((x + CASA / 2, y + CASA / 2 + 2), SIMBOLO[peca.piece_type], font=fonte_peca, anchor="mm",
                       fill=(255, 255, 255) if branca else (20, 20, 20),
                       stroke_width=2, stroke_fill=(20, 20, 20) if branca else (235, 235, 235))

    for i in range(8):
        letra = chess.FILE_NAMES[i if de_baixo == chess.WHITE else 7 - i]
        numero = str(8 - i if de_baixo == chess.WHITE else i + 1)
        centro = MARGEM + i * CASA + CASA / 2
        d.text((centro, lado - MARGEM / 2), letra, font=fonte_coord, anchor="mm", fill=(200, 205, 210))
        d.text((MARGEM / 2, centro), numero, font=fonte_coord, anchor="mm", fill=(200, 205, 210))

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    saida.seek(0)
    return saida


# ============================== CÉREBRO DO BOT ==============================

VALOR = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

# Tabelas de posição (do ponto de vista das brancas, casa a1 = índice 0): incentivam peças no centro,
# peões avançando e o rei protegido.
_PEAO = [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, -20, -20, 10, 10, 5, 5, -5, -10, 0, 0, -10, -5, 5,
         0, 0, 0, 20, 20, 0, 0, 0, 5, 5, 10, 25, 25, 10, 5, 5, 10, 10, 20, 30, 30, 20, 10, 10,
         50, 50, 50, 50, 50, 50, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0]
_CAVALO = [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 5, 5, 0, -20, -40, -30, 5, 10, 15, 15, 10, 5, -30,
           -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 10, 15, 15, 10, 0, -30,
           -40, -20, 0, 0, 0, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50]
_BISPO = [-20, -10, -10, -10, -10, -10, -10, -20, -10, 5, 0, 0, 0, 0, 5, -10, -10, 10, 10, 10, 10, 10, 10, -10,
          -10, 0, 10, 10, 10, 10, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 5, 10, 10, 5, 0, -10,
          -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -10, -10, -10, -10, -20]
_TORRE = [0, 0, 0, 5, 5, 0, 0, 0, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 5, 10, 10, 10, 10, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0]
_DAMA = [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 5, 0, 0, 0, 0, -10, -10, 5, 5, 5, 5, 5, 0, -10,
         0, 0, 5, 5, 5, 5, 0, -5, -5, 0, 5, 5, 5, 5, 0, -5, -10, 0, 5, 5, 5, 5, 0, -10,
         -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20]
_REI = [20, 30, 10, 0, 0, 10, 30, 20, 20, 20, 0, 0, 0, 0, 20, 20, -10, -20, -20, -20, -20, -20, -20, -10,
        -20, -30, -30, -40, -40, -30, -30, -20, -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30]
TABELA = {chess.PAWN: _PEAO, chess.KNIGHT: _CAVALO, chess.BISHOP: _BISPO,
          chess.ROOK: _TORRE, chess.QUEEN: _DAMA, chess.KING: _REI}

MATE = 100_000
NIVEIS = {
    "facil": {"profundidade": 1, "erro": 0.35},
    "medio": {"profundidade": 2, "erro": 0.08},
    "dificil": {"profundidade": 3, "erro": 0.0},
}


def avaliar(tabuleiro: chess.Board) -> int:
    """Nota da posição do ponto de vista de quem joga agora (positivo = bom para ele)."""
    if tabuleiro.is_checkmate():
        return -MATE
    if tabuleiro.is_stalemate() or tabuleiro.is_insufficient_material():
        return 0
    nota = 0
    for casa, peca in tabuleiro.piece_map().items():
        indice = casa if peca.color == chess.WHITE else chess.square_mirror(casa)
        valor = VALOR[peca.piece_type] + TABELA[peca.piece_type][indice]
        nota += valor if peca.color == chess.WHITE else -valor
    return nota if tabuleiro.turn == chess.WHITE else -nota


def _ordenar(tabuleiro: chess.Board) -> List[chess.Move]:
    """Capturas e promoções primeiro: deixa a busca muito mais rápida."""
    def chave(lance):
        if lance.promotion:
            return -1000
        if tabuleiro.is_capture(lance):
            vitima = tabuleiro.piece_at(lance.to_square)
            atacante = tabuleiro.piece_at(lance.from_square)
            return -(VALOR[vitima.piece_type] if vitima else 100) + (VALOR[atacante.piece_type] // 10)
        return 0
    return sorted(tabuleiro.legal_moves, key=chave)


def _negamax(tabuleiro: chess.Board, profundidade: int, alfa: int, beta: int, prazo: float) -> int:
    if profundidade == 0 or tabuleiro.is_game_over():
        return avaliar(tabuleiro)
    if time.monotonic() > prazo:
        return avaliar(tabuleiro)
    melhor = -MATE * 2
    for lance in _ordenar(tabuleiro):
        tabuleiro.push(lance)
        nota = -_negamax(tabuleiro, profundidade - 1, -beta, -alfa, prazo)
        tabuleiro.pop()
        if nota > melhor:
            melhor = nota
        alfa = max(alfa, nota)
        if alfa >= beta:
            break
    return melhor


def melhor_lance(tabuleiro: chess.Board, nivel: str = "medio", limite_segundos: float = 6.0,
                 rng: Optional[random.Random] = None) -> chess.Move:
    """Escolhe o lance do bot. Roda numa thread para não travar o Discord."""
    rng = rng or random.Random()
    config = NIVEIS[nivel]
    lances = list(tabuleiro.legal_moves)
    if rng.random() < config["erro"]:
        return rng.choice(lances)
    prazo = time.monotonic() + limite_segundos
    melhor, melhor_nota = lances[0], -MATE * 3
    tabuleiro = tabuleiro.copy()
    for lance in _ordenar(tabuleiro):
        tabuleiro.push(lance)
        nota = -_negamax(tabuleiro, config["profundidade"] - 1, -MATE * 2, MATE * 2, prazo)
        tabuleiro.pop()
        nota += rng.randint(0, 6)   # um pouco de variedade entre lances parecidos
        if nota > melhor_nota:
            melhor, melhor_nota = lance, nota
    return melhor


def bot_aceita_empate(tabuleiro: chess.Board, cor_do_bot: chess.Color) -> bool:
    nota = avaliar(tabuleiro)
    if tabuleiro.turn != cor_do_bot:
        nota = -nota
    return nota < -150   # só aceita se estiver perdendo
