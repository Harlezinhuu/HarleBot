from conteudo.palavras import PALAVRAS
from conteudo.perguntas import PERGUNTAS
from utils.jogos import MAX_ERROS, Forca, jogada_do_bot, resultado_ppt, vencedor_velha
from utils.niveis import barra, nivel_de, xp_para_subir


# ---------- jogo da velha ----------

def test_vencedor_velha():
    X, O, _ = "X", "O", None
    assert vencedor_velha([X, X, X, _, O, O, _, _, _]) == "X"
    assert vencedor_velha([O, X, X, _, O, X, _, _, O]) == "O"
    assert vencedor_velha([X, O, X, X, O, O, O, X, X]) == "empate"
    assert vencedor_velha([X, _, _, _, O, _, _, _, _]) is None


def test_bot_da_velha_bloqueia_e_vence():
    X, O, _ = "X", "O", None
    # O pode ganhar na casa 2
    assert jogada_do_bot([O, O, _, X, X, _, _, _, _], "O", chance_de_errar=0) == 2
    # X ameaça ganhar na casa 5: o bot precisa bloquear
    assert jogada_do_bot([O, _, _, X, X, _, _, _, _], "O", chance_de_errar=0) == 5


def test_bot_perfeito_nunca_perde():
    """Bot sem erros contra todas as jogadas possíveis do humano: nunca perde."""
    def explorar(tab):
        fim = vencedor_velha(tab)
        if fim:
            assert fim != "X", tab
            return
        for i in range(9):
            if tab[i] is None:
                novo = tab[:]
                novo[i] = "X"
                if not vencedor_velha(novo):
                    novo[jogada_do_bot(novo, "O", chance_de_errar=0)] = "O"
                explorar(novo)
    explorar([None] * 9)


# ---------- forca ----------

def test_forca_com_acento_e_hifen():
    j = Forca("Guarda-chuva", "Objeto")
    assert j.mascara == "_ _ _ _ _ _ - _ _ _ _ _"
    assert j.chutar_letra("A") == "acerto"
    assert j.chutar_letra("a") == "repetida"
    assert j.chutar_letra("1") == "invalida"
    assert j.chutar_letra("z") == "erro" and j.erros == 1

    j2 = Forca("Maracujá", "Fruta")
    j2.chutar_letra("á")  # acento não importa
    assert "Á" in j2.mascara and "A" in j2.mascara
    assert j2.chutar_palavra("maracuja") is True and j2.ganhou


def test_forca_perde():
    j = Forca("Python", "Tecnologia")
    for letra in "abcdefg":
        j.chutar_letra(letra)
    assert j.perdeu and j.erros == MAX_ERROS


# ---------- ppt e níveis ----------

def test_ppt():
    assert resultado_ppt("pedra", "tesoura") == "vitoria"
    assert resultado_ppt("pedra", "papel") == "derrota"
    assert resultado_ppt("papel", "papel") == "empate"


def test_niveis():
    assert nivel_de(0) == (0, 0, 100)
    assert nivel_de(99)[0] == 0
    assert nivel_de(100) == (1, 0, xp_para_subir(1))
    assert nivel_de(100 + 155 + 10) == (2, 10, xp_para_subir(2))
    assert barra(5, 10, 10) == "▰▰▰▰▰▱▱▱▱▱"


# ---------- conteúdo ----------

def test_perguntas_bem_formadas():
    assert len(PERGUNTAS) >= 30
    for p in PERGUNTAS:
        assert len(p["opcoes"]) == 4 and 0 <= p["certa"] < 4, p
        assert len(set(p["opcoes"])) == 4, p
        assert all(len(f"A) {o}") <= 80 for o in p["opcoes"]), p


def test_palavras_jogaveis():
    for categoria, lista in PALAVRAS.items():
        for palavra in lista:
            j = Forca(palavra, categoria)
            assert len(j.palavra) == len(j.base), palavra
            assert "_" in j.mascara, palavra


# ---------- blackjack, minas e batalha ----------

import random as _random

from utils.batalha import Batalha, Lutador
from utils.cassino import CASAS_MINAS, Blackjack, Minas, multiplicador_minas, valor_mao


def test_valor_mao_com_as():
    assert valor_mao([("A", "♠"), ("K", "♥")]) == 21
    assert valor_mao([("A", "♠"), ("A", "♥"), ("9", "♦")]) == 21
    assert valor_mao([("K", "♠"), ("Q", "♥"), ("5", "♦")]) == 25


def test_blackjack_pagamentos_e_regras():
    resultados = set()
    for semente in range(400):
        j = Blackjack(100, _random.Random(semente))
        while not j.acabou:
            j.pedir() if valor_mao(j.jogador) < 15 else j.parar()
        resultados.add(j.resultado)
        if j.resultado != "estourou":
            assert valor_mao(j.mesa) >= 17 or len(j.mesa) == 2
        esperado = {"blackjack": 250, "vitoria": 200, "empate": 100}.get(j.resultado, 0)
        assert j.pagamento == esperado
    assert resultados == {"blackjack", "vitoria", "empate", "derrota", "estourou"}


def test_blackjack_dobrar():
    for semente in range(100):
        j = Blackjack(50, _random.Random(semente))
        if j.pode_dobrar:
            j.dobrar()
            assert j.acabou and j.aposta == 100 and len(j.jogador) == 3
            return
    raise AssertionError("nenhuma mão permitiu dobrar")


def test_minas():
    assert multiplicador_minas(3, 0) == 1.0
    assert multiplicador_minas(3, 1) == round(0.97 * 20 / 17, 2)
    assert multiplicador_minas(8, 3) > multiplicador_minas(3, 3)  # mais bombas paga mais

    m = Minas(100, 3, _random.Random(1))
    segura = next(i for i in range(CASAS_MINAS) if i not in m.bombas)
    assert m.abrir(segura) == "diamante" and m.abrir(segura) == "ja_aberta"
    assert m.premio_atual == int(100 * multiplicador_minas(3, 1))
    assert m.abrir(next(iter(m.bombas))) == "bomba" and m.acabou

    m2 = Minas(100, 3, _random.Random(2))
    seguras = [i for i in range(CASAS_MINAS) if i not in m2.bombas]
    for i in seguras[:-1]:
        assert m2.abrir(i) == "diamante"
    assert m2.abrir(seguras[-1]) == "limpou" and m2.acabou


def test_batalha_ate_o_fim():
    for semente in range(50):
        b = Batalha(Lutador(1, "Ana"), Lutador(2, "Beto"), _random.Random(semente))
        rng = _random.Random(semente + 1000)
        jogadas = 0
        while not b.acabou:
            acao = rng.choice(["atacar", "atacar", "especial", "defender", "curar"])
            b.agir(acao)
            jogadas += 1
            assert jogadas < 500
            for l in b.lutadores:
                assert 0 <= l.vida <= 100 and l.curas >= 0
        assert b.vencedor.vida > 0 and min(l.vida for l in b.lutadores) == 0


def test_batalha_regras():
    b = Batalha(Lutador(1, "Ana"), Lutador(2, "Beto"), _random.Random(0))
    eu = b.atual
    b.agir("especial")
    b.agir("defender")            # o outro defende
    assert b.atual is eu and b.agir("especial") == "O especial ainda está carregando."
    b.desistencia(eu.uid)
    assert b.vencedor is not eu


def test_itens_da_loja():
    from conteudo.itens import CATEGORIAS, ITENS
    for item_id, item in ITENS.items():
        assert item["categoria"] in CATEGORIAS, item_id
        assert item["preco"] > 0 and item["nome"] and item["emoji"], item_id
        if item["categoria"] == "tema":
            assert isinstance(item["cor"], int), item_id
        if item_id in ("boost_xp", "boost_trabalho"):
            assert item["duracao"] > 0


# ---------- música ----------

def test_faixa_de_info():
    from utils.musica import faixa_de_info, formatar_duracao, opcoes_ffmpeg_antes
    yt = faixa_de_info({"id": "abc123", "url": "abc123", "title": "Música", "duration": 185, "ie_key": "Youtube"}, 7)
    assert yt.pagina == "https://www.youtube.com/watch?v=abc123" and yt.fonte == "YouTube" and yt.pedido_por == 7
    sc = faixa_de_info({"url": "https://soundcloud.com/artista/faixa", "title": "Som", "ie_key": "Soundcloud"})
    assert sc.fonte == "SoundCloud" and sc.duracao is None
    assert faixa_de_info({"title": "sem link"}) is None
    assert formatar_duracao(185) == "3:05" and formatar_duracao(3725) == "1:02:05" and formatar_duracao(None) == "ao vivo/?"
    assert "-headers" in opcoes_ffmpeg_antes("-nostdin", {"User-Agent": "x"})
    assert opcoes_ffmpeg_antes("-nostdin", {}) == "-nostdin"
