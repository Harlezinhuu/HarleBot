"""Cards em imagem: perfil e boas-vindas (Pillow)."""
import io
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PASTA = Path(__file__).resolve().parent.parent / "assets"
FUNDO = (22, 24, 29)
FUNDO_2 = (29, 32, 39)
TEXTO = (236, 238, 242)
SUAVE = (154, 161, 173)
LINHA = (44, 48, 57)


# ============================== utilidades ==============================

@lru_cache(maxsize=None)
def fonte(peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    arquivo = {"bold": "Poppins-Bold.ttf", "medium": "Poppins-Medium.ttf",
               "regular": "Poppins-Regular.ttf", "dejavu": "DejaVuSans.ttf"}[peso]
    try:
        return ImageFont.truetype(str(PASTA / "fontes" / arquivo), tamanho)
    except OSError:
        return ImageFont.load_default()


def _letra_ok(c: str) -> bool:
    """Caracteres que a fonte Poppins sabe desenhar (latim, acentos e pontuação comum)."""
    o = ord(c)
    return o < 0x250 or 0x2000 <= o <= 0x206F or c in "€™•…"


def limpar(texto: str) -> str:
    """Tira emojis e símbolos que a fonte não desenha (eles virariam quadradinhos)."""
    saida = []
    for c in texto or "":
        if _letra_ok(c):
            saida.append(c)
        elif unicodedata.category(c).startswith("L"):
            saida.append(c)  # letras de outros alfabetos: desenhadas com a DejaVu
    return " ".join("".join(saida).split())


def fonte_para(texto: str, peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    return fonte(peso, tamanho) if all(_letra_ok(c) for c in texto) else fonte("dejavu", tamanho)


def cortar_para_caber(d: ImageDraw.ImageDraw, texto: str, f, largura: int) -> str:
    if d.textlength(texto, font=f) <= largura:
        return texto
    while texto and d.textlength(texto + "…", font=f) > largura:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def quebrar_linhas(d: ImageDraw.ImageDraw, texto: str, f, largura: int, max_linhas: int) -> List[str]:
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if d.textlength(teste, font=f) <= largura:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
        if len(linhas) == max_linhas:
            break
    if atual and len(linhas) < max_linhas:
        linhas.append(atual)
    if len(linhas) == max_linhas and " ".join(linhas) != " ".join(palavras):
        linhas[-1] = cortar_para_caber(d, linhas[-1] + " …", f, largura)
    return linhas


@lru_cache(maxsize=256)
def _emoji_cru(emoji: str) -> Optional[Image.Image]:
    nome = "-".join(f"{ord(c):x}" for c in emoji if ord(c) != 0xFE0F)
    arquivo = PASTA / "emojis" / f"{nome}.png"
    return Image.open(arquivo).convert("RGBA") if arquivo.exists() else None


def emoji(emoji_txt: str, tamanho: int) -> Optional[Image.Image]:
    img = _emoji_cru(emoji_txt)
    return img.resize((tamanho, tamanho), Image.LANCZOS) if img else None


def avatar_redondo(dados: Optional[bytes], tamanho: int, cor_anel: Tuple[int, int, int], letra: str) -> Image.Image:
    """Avatar em círculo com anel colorido. Sem imagem, desenha a inicial do nome."""
    borda = max(4, tamanho // 28)
    final = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    ImageDraw.Draw(final).ellipse([0, 0, tamanho - 1, tamanho - 1], fill=cor_anel)
    interno = tamanho - borda * 2
    try:
        foto = Image.open(io.BytesIO(dados)).convert("RGBA").resize((interno, interno), Image.LANCZOS)
    except Exception:
        foto = Image.new("RGBA", (interno, interno), FUNDO_2)
        d = ImageDraw.Draw(foto)
        d.text((interno / 2, interno / 2), (letra or "?")[:1].upper(), font=fonte("bold", interno // 2),
               anchor="mm", fill=TEXTO)
    mascara = Image.new("L", (interno * 4, interno * 4), 0)
    ImageDraw.Draw(mascara).ellipse([0, 0, interno * 4 - 1, interno * 4 - 1], fill=255)
    mascara = mascara.resize((interno, interno), Image.LANCZOS)
    final.paste(foto, (borda, borda), mascara)
    return final


def rgb(cor: int) -> Tuple[int, int, int]:
    return (cor >> 16) & 255, (cor >> 8) & 255, cor & 255


def misturar(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _fundo_com_brilho(largura: int, altura: int, cor: Tuple[int, int, int], centro: bool = False) -> Image.Image:
    img = Image.new("RGB", (largura, altura), FUNDO)
    brilho = Image.new("RGB", (largura, altura), FUNDO)
    d = ImageDraw.Draw(brilho)
    if centro:
        caixa = [largura * 0.2, -altura * 0.6, largura * 0.8, altura * 0.85]
    else:
        caixa = [-largura * 0.15, -altura * 0.9, largura * 0.55, altura * 0.75]
    d.ellipse(caixa, fill=misturar(FUNDO, cor, 0.35))
    brilho = brilho.filter(ImageFilter.GaussianBlur(90))
    return Image.blend(img, brilho, 1.0)


def _png(img: Image.Image) -> io.BytesIO:
    saida = io.BytesIO()
    img.save(saida, "PNG")
    saida.seek(0)
    return saida


# ============================== perfil ==============================

def desenhar_perfil(*, nome: str, avatar: Optional[bytes], cor: int, emoji_tema: Optional[str],
                    titulo: Optional[str], emoji_titulo: Optional[str], sobre: Optional[str], nivel: int,
                    xp_atual: int, xp_precisa: int, posicao: int, moedas: int, sequencia: int,
                    insignias: List[str], conquistas: List[str], total_conquistas: int) -> io.BytesIO:
    L, A = 1000, 460
    destaque = rgb(cor)
    img = _fundo_com_brilho(L, A, destaque).convert("RGBA")
    d = ImageDraw.Draw(img)

    # faixa de cor no topo
    d.rectangle([0, 0, L, 8], fill=destaque)

    # avatar
    av = avatar_redondo(avatar, 190, destaque, nome)
    img.alpha_composite(av, (48, 52))

    # nome e título
    x = 270
    nome_limpo = limpar(nome) or "Membro"
    f_nome = fonte_para(nome_limpo, "bold", 46)
    d.text((x, 58), cortar_para_caber(d, nome_limpo, f_nome, L - x - 110), font=f_nome, fill=TEXTO)
    y = 122
    if titulo:
        if emoji_titulo and (e := emoji(emoji_titulo, 28)):
            img.alpha_composite(e, (x, y + 2))
            tx = x + 38
        else:
            tx = x
        d.text((tx, y), limpar(titulo), font=fonte("medium", 24), fill=destaque)
        y += 44
    if emoji_tema and (e := emoji(emoji_tema, 54)):
        img.alpha_composite(e, (L - 54 - 40, 52))

    # sobre mim
    f_sobre = fonte("regular", 21)
    texto_sobre = limpar(sobre) if sobre else "Sem \"sobre mim\" ainda. Use /sobremim para escrever o seu."
    cor_sobre = TEXTO if sobre else SUAVE
    for linha in quebrar_linhas(d, texto_sobre, fonte_para(texto_sobre, "regular", 21), L - x - 50, 3):
        d.text((x, y), linha, font=fonte_para(texto_sobre, "regular", 21) if sobre else f_sobre, fill=cor_sobre)
        y += 31

    # números
    y_num = 272
    colunas = [("NÍVEL", f"{nivel}"), ("RANKING", f"#{posicao}"),
               ("HARLECOINS", f"{moedas:,}".replace(",", ".")), ("DAILY", f"{sequencia} dias")]
    largura_col = (L - 96) / 4
    for i, (rotulo, valor) in enumerate(colunas):
        cx = 48 + i * largura_col
        d.rounded_rectangle([cx, y_num, cx + largura_col - 14, y_num + 74], radius=14, fill=FUNDO_2, outline=LINHA)
        d.text((cx + 18, y_num + 12), rotulo, font=fonte("medium", 14), fill=SUAVE)
        d.text((cx + 18, y_num + 32), valor, font=fonte("bold", 26), fill=TEXTO)

    # barra de XP
    y_bar = 370
    d.text((48, y_bar - 4), f"XP para o nível {nivel + 1}", font=fonte("medium", 15), fill=SUAVE)
    texto_xp = f"{xp_atual:,} / {xp_precisa:,}".replace(",", ".")
    d.text((L - 48, y_bar - 4), texto_xp, font=fonte("medium", 15), fill=SUAVE, anchor="ra")
    d.rounded_rectangle([48, y_bar + 22, L - 48, y_bar + 38], radius=8, fill=FUNDO_2)
    if xp_precisa > 0 and xp_atual > 0:
        fim = 48 + (L - 96) * min(1, xp_atual / xp_precisa)
        d.rounded_rectangle([48, y_bar + 22, max(fim, 64), y_bar + 38], radius=8, fill=destaque)

    # insígnias e conquistas (rodapé)
    y_ic = 418
    icones = insignias + conquistas
    xi = 48
    for e_txt in icones[:22]:
        if e := emoji(e_txt, 28):
            img.alpha_composite(e, (int(xi), y_ic))
            xi += 36
    resumo = f"{len(conquistas)}/{total_conquistas} conquistas"
    d.text((L - 48, y_ic + 4), resumo, font=fonte("medium", 15), fill=SUAVE, anchor="ra")
    if not icones:
        d.text((48, y_ic + 4), "Nenhuma insígnia ainda: veja a /loja e as /conquistas", font=fonte("regular", 15),
               fill=SUAVE)

    return _png(img.convert("RGB"))


# ============================== boas-vindas ==============================

def desenhar_boasvindas(*, nome: str, avatar: Optional[bytes], servidor: str, numero: int,
                        cor: int = 0x4C8DFF) -> io.BytesIO:
    L, A = 1000, 380
    destaque = rgb(cor)
    img = _fundo_com_brilho(L, A, destaque, centro=True).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.rectangle([0, A - 8, L, A], fill=destaque)

    av = avatar_redondo(avatar, 170, destaque, nome)
    img.alpha_composite(av, ((L - 170) // 2, 34))

    d.text((L / 2, 228), "BEM-VINDO(A)", font=fonte("medium", 22), fill=destaque, anchor="mm")
    nome_limpo = limpar(nome) or "Novo membro"
    f_nome = fonte_para(nome_limpo, "bold", 44)
    d.text((L / 2, 270), cortar_para_caber(d, nome_limpo, f_nome, L - 120), font=f_nome, fill=TEXTO, anchor="mm")
    servidor_limpo = limpar(servidor) or "servidor"
    texto = f"Você é o membro nº {numero:,} de {servidor_limpo}".replace(",", ".")
    f_txt = fonte_para(texto, "regular", 22)
    d.text((L / 2, 318), cortar_para_caber(d, texto, f_txt, L - 120), font=f_txt, fill=SUAVE, anchor="mm")
    return _png(img.convert("RGB"))
