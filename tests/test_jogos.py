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
