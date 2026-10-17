from datetime import timedelta

from utils.tempo import converter, formatar


def test_converte_formatos_comuns():
    assert converter("10m") == timedelta(minutes=10)
    assert converter("1h30m") == timedelta(hours=1, minutes=30)
    assert converter("2d") == timedelta(days=2)
    assert converter("1 h 15 min") == timedelta(hours=1, minutes=15)
    assert converter("1sem") == timedelta(weeks=1)


def test_recusa_textos_invalidos():
    for texto in ["", "abc", "10", "10x", "h1", "0m", "1h banana"]:
        assert converter(texto) is None, texto


def test_formata_em_portugues():
    assert formatar(timedelta(minutes=1)) == "1 minuto"
    assert formatar(timedelta(hours=1, minutes=30)) == "1 hora e 30 minutos"
    assert formatar(timedelta(days=2, hours=1, seconds=5)) == "2 dias, 1 hora e 5 segundos"
