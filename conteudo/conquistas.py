"""Conquistas: insígnias que se ganha jogando. Para criar uma nova, copie uma linha.

`stat` é o contador que precisa chegar em `meta`. `premio` é quanto a pessoa ganha ao desbloquear.
Os contadores "max_" guardam o maior valor já alcançado (ex.: maior nível), os outros somam.
"""

CONQUISTAS = [
    # ---------- quiz e jogos rápidos ----------
    {"id": "quiz_1", "nome": "Sabe-tudo iniciante", "emoji": "🧠", "stat": "quiz_acertos", "meta": 1, "premio": 50,
     "descricao": "Acerte uma pergunta do /quiz"},
    {"id": "quiz_50", "nome": "Enciclopédia", "emoji": "📚", "stat": "quiz_acertos", "meta": 50, "premio": 1000,
     "descricao": "Acerte 50 perguntas do /quiz"},
    {"id": "forca_10", "nome": "Carrasco", "emoji": "🪢", "stat": "forca_vitorias", "meta": 10, "premio": 500,
     "descricao": "Complete 10 palavras na /forca"},
    {"id": "velha_10", "nome": "Velha de guerra", "emoji": "❌", "stat": "velha_vitorias", "meta": 10, "premio": 500,
     "descricao": "Vença 10 partidas de /velha"},
    {"id": "velha_impossivel", "nome": "Segurou o impossível", "emoji": "🧱", "stat": "velha_empate_impossivel",
     "meta": 1, "premio": 300, "descricao": "Empate com o bot no nível impossível"},
    {"id": "ppt_25", "nome": "Mão de pedra", "emoji": "🪨", "stat": "ppt_vitorias", "meta": 25, "premio": 500,
     "descricao": "Vença 25 partidas de /ppt"},

    # ---------- truco e xadrez ----------
    {"id": "truco_1", "nome": "Truco ladrão!", "emoji": "🃏", "stat": "truco_vitorias", "meta": 1, "premio": 200,
     "descricao": "Vença uma partida de /truco"},
    {"id": "truco_10", "nome": "Zap na manga", "emoji": "♣️", "stat": "truco_vitorias", "meta": 10, "premio": 1500,
     "descricao": "Vença 10 partidas de /truco"},
    {"id": "truco_50", "nome": "Lenda do boteco", "emoji": "🍺", "stat": "truco_vitorias", "meta": 50, "premio": 6000,
     "descricao": "Vença 50 partidas de /truco"},
    {"id": "xadrez_1", "nome": "Primeiro xeque-mate", "emoji": "♟️", "stat": "xadrez_vitorias", "meta": 1,
     "premio": 300, "descricao": "Vença uma partida de /xadrez"},
    {"id": "xadrez_10", "nome": "Grande mestre", "emoji": "👑", "stat": "xadrez_vitorias", "meta": 10, "premio": 3000,
     "descricao": "Vença 10 partidas de /xadrez"},
    {"id": "xadrez_dificil", "nome": "Venceu a máquina", "emoji": "🤖", "stat": "xadrez_bot_dificil", "meta": 1,
     "premio": 2500, "descricao": "Vença o bot no /xadrez difícil"},

    # ---------- cassino e batalha ----------
    {"id": "blackjack", "nome": "Vinte e um!", "emoji": "♠️", "stat": "blackjack_naturais", "meta": 1, "premio": 300,
     "descricao": "Tire um blackjack de cara no /blackjack"},
    {"id": "blackjack_25", "nome": "Conta cartas", "emoji": "🎰", "stat": "blackjack_vitorias", "meta": 25,
     "premio": 1500, "descricao": "Vença 25 mãos de /blackjack"},
    {"id": "minas_limpou", "nome": "Desarmador", "emoji": "💣", "stat": "minas_limpou", "meta": 1, "premio": 1000,
     "descricao": "Abra todas as casas seguras do /minas"},
    {"id": "batalha_10", "nome": "Gladiador", "emoji": "⚔️", "stat": "batalha_vitorias", "meta": 10, "premio": 1000,
     "descricao": "Vença 10 /batalha"},

    # ---------- dedicação ----------
    {"id": "daily_7", "nome": "Fiel", "emoji": "📅", "stat": "max_daily_sequencia", "meta": 7, "premio": 500,
     "descricao": "Pegue o /daily 7 dias seguidos"},
    {"id": "daily_30", "nome": "Assinante", "emoji": "🗓️", "stat": "max_daily_sequencia", "meta": 30, "premio": 3000,
     "descricao": "Pegue o /daily 30 dias seguidos"},
    {"id": "nivel_10", "nome": "Tagarela", "emoji": "💬", "stat": "max_nivel", "meta": 10, "premio": 1000,
     "descricao": "Chegue ao nível 10 conversando"},
    {"id": "nivel_25", "nome": "Voz do servidor", "emoji": "📣", "stat": "max_nivel", "meta": 25, "premio": 5000,
     "descricao": "Chegue ao nível 25"},
    {"id": "rico", "nome": "Primeiro milhão", "emoji": "💰", "stat": "max_moedas", "meta": 1_000_000, "premio": 0,
     "descricao": "Junte 1.000.000 de Harlecoins"},
]

POR_ID = {c["id"]: c for c in CONQUISTAS}
