"""Itens da loja do bot. Para criar um item novo, copie uma linha e mude os dados.

Categorias:
- tema:     muda a cor e o emoji do seu /perfil
- insignia: aparece no seu /perfil (todas que você tiver)
- titulo:   frase que aparece embaixo do seu nome no /perfil
- boost:    consumível; ative com /usar (o daily em dobro é usado sozinho no próximo /daily)
"""

CATEGORIAS = {
    "tema": ("🎨", "Temas de perfil"),
    "insignia": ("🏅", "Insígnias"),
    "titulo": ("🏷️", "Títulos"),
    "boost": ("⚡", "Boosts"),
}

ITENS = {
    # ---------- temas ----------
    "tema_neon":     {"categoria": "tema", "nome": "Neon Azul", "emoji": "💠", "preco": 1500, "cor": 0x00E5FF},
    "tema_sakura":   {"categoria": "tema", "nome": "Sakura", "emoji": "🌸", "preco": 1500, "cor": 0xFF8FC7},
    "tema_floresta": {"categoria": "tema", "nome": "Floresta", "emoji": "🌲", "preco": 2000, "cor": 0x2ECC71},
    "tema_fogo":     {"categoria": "tema", "nome": "Fogo", "emoji": "🔥", "preco": 2000, "cor": 0xFF5722},
    "tema_oceano":   {"categoria": "tema", "nome": "Oceano", "emoji": "🌊", "preco": 2500, "cor": 0x1565C0},
    "tema_galaxia":  {"categoria": "tema", "nome": "Galáxia", "emoji": "🌌", "preco": 3000, "cor": 0x7C4DFF},
    "tema_vampiro":  {"categoria": "tema", "nome": "Vampiro", "emoji": "🦇", "preco": 3500, "cor": 0x8B0000},
    "tema_ouro":     {"categoria": "tema", "nome": "Ouro", "emoji": "✨", "preco": 6000, "cor": 0xF5C542},

    # ---------- insígnias ----------
    "ins_cafe":     {"categoria": "insignia", "nome": "Viciado em Café", "emoji": "☕", "preco": 600},
    "ins_gato":     {"categoria": "insignia", "nome": "Amante de Gatos", "emoji": "🐱", "preco": 600},
    "ins_cachorro": {"categoria": "insignia", "nome": "Amante de Cachorros", "emoji": "🐶", "preco": 600},
    "ins_pizza":    {"categoria": "insignia", "nome": "Pizzaiolo", "emoji": "🍕", "preco": 700},
    "ins_gamer":    {"categoria": "insignia", "nome": "Gamer", "emoji": "🎮", "preco": 800},
    "ins_musica":   {"categoria": "insignia", "nome": "Melômano", "emoji": "🎧", "preco": 800},
    "ins_dev":      {"categoria": "insignia", "nome": "Programador", "emoji": "💻", "preco": 1000},
    "ins_alien":    {"categoria": "insignia", "nome": "Alienígena", "emoji": "👽", "preco": 1500},
    "ins_dragao":   {"categoria": "insignia", "nome": "Dragão", "emoji": "🐉", "preco": 2500},
    "ins_coroa":    {"categoria": "insignia", "nome": "Realeza", "emoji": "👑", "preco": 5000},
    "ins_diamante": {"categoria": "insignia", "nome": "Diamante", "emoji": "💎", "preco": 10000},

    # ---------- títulos ----------
    "tit_coruja":     {"categoria": "titulo", "nome": "Coruja Noturna", "emoji": "🦉", "preco": 1500},
    "tit_gamer":      {"categoria": "titulo", "nome": "Gamer Raiz", "emoji": "🕹️", "preco": 1500},
    "tit_misterioso": {"categoria": "titulo", "nome": "Misterioso", "emoji": "🕵️", "preco": 2000},
    "tit_quiz":       {"categoria": "titulo", "nome": "Mestre do Quiz", "emoji": "🧠", "preco": 2500},
    "tit_cassino":    {"categoria": "titulo", "nome": "Lenda do Cassino", "emoji": "🎰", "preco": 3000},
    "tit_guerreiro":  {"categoria": "titulo", "nome": "Guerreiro Invicto", "emoji": "⚔️", "preco": 3000},
    "tit_lenda":      {"categoria": "titulo", "nome": "A Lenda", "emoji": "🌟", "preco": 5000},
    "tit_milionario": {"categoria": "titulo", "nome": "Milionário", "emoji": "💰", "preco": 25000},

    # ---------- boosts (consumíveis) ----------
    "boost_xp":       {"categoria": "boost", "nome": "XP em dobro (1 hora)", "emoji": "⚡", "preco": 800,
                       "duracao": 3600},
    "boost_trabalho": {"categoria": "boost", "nome": "Salário em dobro (1 hora)", "emoji": "💼", "preco": 600,
                       "duracao": 3600},
    "boost_daily":    {"categoria": "boost", "nome": "Daily em dobro (próximo daily)", "emoji": "🎁", "preco": 700},
}


def eh_consumivel(item_id: str) -> bool:
    return ITENS[item_id]["categoria"] == "boost"


def rotulo(item_id: str) -> str:
    item = ITENS[item_id]
    return f"{item['emoji']} {item['nome']}"
