import asyncio

from core.db import Database


def rodar(coro):
    return asyncio.run(coro)


def test_avisos_e_casos():
    async def cenario():
        db = Database(":memory:")
        await db.connect()

        assert await db.get_log_channel(1) is None
        await db.set_log_channel(1, 99)
        assert await db.get_log_channel(1) == 99
        await db.set_log_channel(1, None)
        assert await db.get_log_channel(1) is None

        a = await db.add_warning(1, 10, 20, "spam")
        await db.add_warning(1, 10, 20, "flood")
        await db.add_warning(2, 10, 20, "outro servidor")
        assert len(await db.list_warnings(1, 10)) == 2
        assert await db.remove_warning(2, a) is False  # aviso de outro servidor
        assert await db.remove_warning(1, a) is True
        assert await db.clear_warnings(1, 10) == 1

        assert await db.add_case(1, "ban", 10, 20, None) == 1
        assert await db.add_case(1, "kick", 11, 20, "x") == 2
        assert await db.add_case(2, "ban", 10, 20, None) == 1  # cada servidor conta do 1
        await db.close()

    rodar(cenario())


def test_economia_e_niveis():
    async def cenario():
        db = Database(":memory:")
        await db.connect()

        assert (await db.get_wallet(1, 10))["coins"] == 0
        assert await db.add_coins(1, 10, 100) == 100
        assert await db.add_coins(1, 10, -500) == 0          # nunca fica negativo
        await db.add_coins(1, 10, 100)
        assert await db.spend_coins(1, 10, 150) is False     # não tem o suficiente
        assert await db.transfer(1, 10, 20, 60) is True
        assert (await db.get_wallet(1, 10))["coins"] == 40
        assert (await db.get_wallet(1, 20))["coins"] == 60
        assert [r["user_id"] for r in await db.top_coins(1)] == [20, 10]

        await db.set_daily(1, 10, 1000, 3)
        carteira = await db.get_wallet(1, 10)
        assert carteira["last_daily"] == 1000 and carteira["streak"] == 3

        await db.shop_add(1, 555, 300)
        await db.shop_add(1, 555, 250)                       # muda o preço
        assert (await db.shop_get(1, 555))["price"] == 250
        assert await db.shop_remove(1, 555) is True

        assert await db.add_xp(1, 10, 20) == (0, 20)
        assert await db.add_xp(1, 10, 30) == (20, 50)
        await db.add_xp(1, 20, 80)
        assert await db.xp_rank(1, 20) == 1 and await db.xp_rank(1, 10) == 2

        await db.reward_set(1, 5, 777)
        assert [r["level"] for r in await db.rewards_list(1)] == [5]
        assert await db.get_level_settings(1) == (True, None)
        await db.set_level_settings(1, False, 999)
        assert await db.get_level_settings(1) == (False, 999)
        await db.close()

    rodar(cenario())
