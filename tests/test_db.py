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
