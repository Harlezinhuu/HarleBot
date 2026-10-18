import asyncio

from core.db import Database
from utils.protecao import (ContadorDeInfracoes, DetectorDeRaid, DetectorDeSpam, analisar_mensagem,
                            excesso_de_maiusculas, palavra_proibida, tem_convite, tem_link)

TUDO = {"anti_links": 1, "anti_convites": 1, "anti_caps": 1, "anti_mencoes": 1, "limite_mencoes": 5}


def test_detectores_de_texto():
    assert tem_link("olha https://site.com") and tem_link("www.site.com") and not tem_link("site sem link")
    assert tem_convite("entra discord.gg/abc123") and tem_convite("https://discord.com/invite/xyz")
    assert excesso_de_maiusculas("VOCÊS SÃO MUITO CHATOS DEMAIS")
    assert not excesso_de_maiusculas("OI GENTE")              # curta demais para contar
    assert not excesso_de_maiusculas("Olá, tudo bem com vocês hoje?")
    assert palavra_proibida("Que PALAVRÃO feio", ["palavrao"]) == "palavrao"   # ignora acento e caixa
    assert palavra_proibida("palavraozinho", ["palavrao"]) is None              # só a palavra inteira
    assert palavra_proibida("isso é muito ruim", ["muito ruim"]) == "muito ruim"


def test_analise_completa():
    assert analisar_mensagem("entra aí discord.gg/abc", 0, TUDO, []) == "convite de outro servidor"
    assert analisar_mensagem("https://site.com", 0, TUDO, []) == "link"
    assert analisar_mensagem("oi", 6, TUDO, []) == "excesso de menções"
    assert analisar_mensagem("mensagem normal", 1, TUDO, ["feio"]) is None
    assert analisar_mensagem("https://site.com", 0, {**TUDO, "anti_links": 0}, []) is None


def test_spam_e_infracoes():
    d = DetectorDeSpam(maximo=5, janela=5, repeticoes=3)
    assert not any(d.registrar(1, 1, f"msg {i}", agora=i * 0.1) for i in range(5))
    assert d.registrar(1, 1, "msg 6", agora=0.6)                # 6ª mensagem em menos de 5s
    assert not d.registrar(1, 2, "oi", agora=1) and not d.registrar(1, 2, "oi", agora=10)
    assert d.registrar(1, 2, "oi", agora=20)                    # mesma mensagem 3 vezes
    c = ContadorDeInfracoes(janela=60)
    assert [c.somar(1, 1, agora=t) for t in (0, 10, 20)] == [1, 2, 3]
    assert c.somar(1, 1, agora=200) == 1                         # as antigas expiraram


def test_raid():
    r = DetectorDeRaid()
    assert not any(r.registrar(1, limite=5, janela=10, agora=t) for t in range(4))
    assert r.registrar(1, limite=5, janela=10, agora=4)
    r.limpar(1)
    assert not r.registrar(1, limite=5, janela=10, agora=100)


def test_banco_protecao_e_paineis():
    async def cenario():
        db = Database(":memory:")
        await db.connect()
        assert (await db.get_automod(1))["ativo"] == 0
        await db.set_automod(1, ativo=True, anti_links=True, punicao="avisar", anti_caps=None)
        c = await db.get_automod(1)
        assert c["ativo"] == 1 and c["anti_links"] == 1 and c["punicao"] == "avisar" and c["anti_caps"] == 0
        await db.palavra_adicionar(1, "feio")
        assert await db.palavras_proibidas(1) == ["feio"]
        assert await db.alternar_ignorado(1, 99) is True and await db.ignorados(1) == [99]
        assert await db.alternar_ignorado(1, 99) is False and await db.ignorados(1) == []
        await db.set_antiraid(1, ativo=True, limite=5)
        assert (await db.get_antiraid(1))["limite"] == 5
        await db.painel_criar(500, 1, 10, "Jogos", None, "reacoes", True)
        await db.painel_item_salvar(500, 7, "🎮", None)
        await db.painel_item_salvar(500, 8, "⚽", "Futebol")
        await db.painel_item_salvar(500, 7, "🕹️", None)          # atualiza o emoji
        assert [(i["role_id"], i["emoji"]) for i in await db.painel_itens(500)] == [(7, "🕹️"), (8, "⚽")]
        assert (await db.painel(500))["unico"] == 1
        await db.painel_apagar(500)
        assert await db.painel(500) is None and await db.painel_itens(500) == []
        await db.close()
    asyncio.run(cenario())
