import chess

from utils.xadrez import desenhar, lance_em_portugues, ler_lance, melhor_lance


def test_notacao_em_portugues():
    t = chess.Board()
    assert lance_em_portugues(t, chess.Move.from_uci("g1f3")) == "Cf3"
    assert ler_lance(t, "Cf3") == chess.Move.from_uci("g1f3")
    assert ler_lance(t, "Nf3") == chess.Move.from_uci("g1f3")      # inglês também vale
    assert ler_lance(t, "e2e4") == chess.Move.from_uci("e2e4")
    assert ler_lance(t, "e5") is None                               # lance impossível
    promo = chess.Board("8/4P3/8/8/8/8/k7/7K w - - 0 1")
    assert ler_lance(promo, "e8=D") == chess.Move.from_uci("e7e8q")
    assert lance_em_portugues(promo, chess.Move.from_uci("e7e8q")).startswith("e8=D")


def test_bot_acha_mate_em_um():
    t = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    for nivel in ("medio", "dificil"):
        lance = melhor_lance(t, nivel)
        t.push(lance)
        assert t.is_checkmate(), nivel
        t.pop()


def test_desenho_gera_png():
    imagem = desenhar(chess.Board(), chess.BLACK).getvalue()
    assert imagem[:8] == b"\x89PNG\r\n\x1a\n" and len(imagem) > 5000
