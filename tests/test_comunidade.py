import asyncio

from conteudo.conquistas import CONQUISTAS, POR_ID
from core.db import Database


def test_catalogo_de_conquistas():
    ids = [c["id"] for c in CONQUISTAS]
    assert len(ids) == len(set(ids)) == len(POR_ID)
    for c in CONQUISTAS:
        assert c["meta"] > 0 and c["premio"] >= 0 and c["nome"] and c["emoji"] and c["descricao"]


def test_imagens_dos_emojis_existem():
    from conteudo.itens import ITENS
    from utils.cards import emoji
    for e in [c["emoji"] for c in CONQUISTAS] + [i["emoji"] for i in ITENS.values()]:
        assert emoji(e, 28) is not None, e


def test_banco_stats_sorteios_tickets():
    async def cenario():
        db = Database(":memory:")
        await db.connect()
        assert await db.stat_somar(1, 5, "truco_vitorias") == 1
        assert await db.stat_somar(1, 5, "truco_vitorias", 2) == 3
        assert await db.stat_maximo(1, 5, "max_nivel", 7) == 7
        assert await db.stat_maximo(1, 5, "max_nivel", 3) == 7          # máximo não diminui
        assert await db.stats(1, 5) == {"truco_vitorias": 3, "max_nivel": 7}
        assert await db.conquista_desbloquear(1, 5, "truco_1") is True
        assert await db.conquista_desbloquear(1, 5, "truco_1") is False
        assert await db.conquistas(1, 5) == ["truco_1"]

        await db.set_welcome(1, 10, "oi {membro}", None)
        assert (await db.get_welcome(1))["channel_id"] == 10
        await db.set_welcome(1, None)
        assert await db.get_welcome(1) is None

        await db.sorteio_criar(900, 1, 10, 5, "Nitro", 100, None, 2, termina=50)
        assert await db.sorteio_entrar(900, 7) is True and await db.sorteio_entrar(900, 8) is True
        assert await db.sorteio_entrar(900, 8) is False                   # clicar de novo sai
        assert await db.sorteio_participantes(900) == [7]
        assert [s["message_id"] for s in await db.sorteios_vencidos(49)] == []
        assert [s["message_id"] for s in await db.sorteios_vencidos(50)] == [900]
        assert await db.sorteio_encerrar(900) is True and await db.sorteio_encerrar(900) is False
        assert await db.sorteios_vencidos(100) == []

        await db.set_ticket_config(1, 20, 30)
        assert await db.ticket_proximo_numero(1) == 1 and await db.ticket_proximo_numero(1) == 2
        await db.ticket_abrir(111, 1, 5, 2)
        assert (await db.ticket_aberto_de(1, 5))["numero"] == 2
        await db.ticket_fechar(111)
        assert await db.ticket_aberto_de(1, 5) is None
        await db.close()
    asyncio.run(cenario())
