"""Busca de músicas com yt-dlp (YouTube e SoundCloud) e utilidades."""
import glob
import logging
import os
import re
import shlex
import shutil
import sys
import sysconfig
from dataclasses import dataclass, field
from typing import Dict, List, Optional

LIMITE_PLAYLIST = 50
log = logging.getLogger("harle.musica")
URL = re.compile(r"^https?://", re.I)


@dataclass
class Faixa:
    titulo: str
    pagina: str                      # link da página (YouTube/SoundCloud)
    fonte: str                       # "YouTube" ou "SoundCloud"
    duracao: Optional[int] = None    # segundos
    thumb: Optional[str] = None
    pedido_por: int = 0              # id de quem pediu
    stream: Optional[str] = field(default=None, repr=False)
    headers: Dict[str, str] = field(default_factory=dict, repr=False)


def formatar_duracao(segundos: Optional[float]) -> str:
    if not segundos:
        return "ao vivo/?"
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fonte(info: Dict) -> str:
    chave = (info.get("ie_key") or info.get("extractor_key") or info.get("extractor") or "").lower()
    pagina = (info.get("webpage_url") or info.get("url") or "").lower()
    if "soundcloud" in chave or "soundcloud.com" in pagina:
        return "SoundCloud"
    return "YouTube"


def faixa_de_info(info: Dict, pedido_por: int = 0) -> Optional[Faixa]:
    """Transforma o resultado do yt-dlp numa Faixa. Devolve None se faltar o essencial."""
    fonte = _fonte(info)
    pagina = info.get("webpage_url") or info.get("original_url") or info.get("url") or ""
    if pagina and not URL.match(pagina):
        if fonte == "YouTube" and info.get("id"):
            pagina = f"https://www.youtube.com/watch?v={info['id']}"
        else:
            return None
    if not pagina:
        return None
    thumb = info.get("thumbnail")
    if not thumb and info.get("thumbnails"):
        thumb = info["thumbnails"][-1].get("url")
    return Faixa(
        titulo=info.get("title") or "Sem título",
        pagina=pagina,
        fonte=fonte,
        duracao=int(info["duration"]) if info.get("duration") else None,
        thumb=thumb,
        pedido_por=pedido_por,
    )


# ---------------------- ferramentas externas ----------------------

def achar_ffmpeg() -> str:
    """Usa o FFmpeg que vem no pacote imageio-ffmpeg; se não tiver, o do sistema."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def achar_deno() -> Optional[str]:
    """O YouTube exige um motor de JavaScript; o pacote 'deno' do pip traz um."""
    caminho = shutil.which("deno")
    if caminho:
        return caminho
    try:
        import deno  # type: ignore
        for nome in ("find_deno_bin", "find_deno"):
            if hasattr(deno, nome):
                return getattr(deno, nome)()
    except Exception:
        pass
    pastas = {sysconfig.get_path("scripts"), os.path.dirname(sys.executable), os.path.expanduser("~/.local/bin")}
    for pasta in pastas:
        for candidato in glob.glob(os.path.join(pasta or "", "deno*")):
            if os.access(candidato, os.X_OK):
                return candidato
    return None


def opcoes_ffmpeg_antes(base: str, headers: Dict[str, str]) -> str:
    """Opções do FFmpeg antes da entrada, incluindo os cabeçalhos que o site exige."""
    if not headers:
        return base
    texto = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    return f"{base} -headers {shlex.quote(texto)}"


def arquivo_cookies() -> Optional[str]:
    """Cookies do YouTube (opcional). Ajuda quando o YouTube bloqueia o servidor."""
    caminho = os.getenv("YOUTUBE_COOKIES") or "cookies.txt"
    return caminho if os.path.isfile(caminho) else None


def limpar_titulo(titulo: str) -> str:
    """'3. Thiago x Leozin - Captura (Prod. Neco) [Clipe]' -> 'Thiago x Leozin - Captura'"""
    t = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", titulo)      # tira (…) [...] {...}
    t = re.sub(r"^\s*\d+\s*[\.\-\)]\s*", "", t)                   # tira numeração do começo
    t = re.split(r"\s[|•]\s", t)[0]                                 # tira o que vem depois de | ou •
    t = re.sub(r"\b(official|oficial|video|vídeo|clipe|lyrics?|audio|áudio|visualizer|hd|4k)\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" -–") or titulo


def opcoes_ytdl(**extra) -> Dict:
    opcoes = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "source_address": "0.0.0.0",
        "socket_timeout": 15,
    }
    deno = achar_deno()
    if deno:
        opcoes["js_runtimes"] = {"deno": {"path": deno}}
    cookies = arquivo_cookies()
    if cookies:
        opcoes["cookiefile"] = cookies
    opcoes.update(extra)
    return opcoes


# ---------------------- busca (roda numa thread) ----------------------

def buscar(texto: str, fonte: str, pedido_por: int) -> List[Faixa]:
    """Procura por link ou por texto. `fonte`: 'youtube' ou 'soundcloud'. Pode lançar exceção."""
    import yt_dlp

    texto = texto.strip()
    if URL.match(texto):
        alvo = texto
        opcoes = opcoes_ytdl(extract_flat="in_playlist", noplaylist=False, playlistend=LIMITE_PLAYLIST)
    else:
        alvo = f"{'scsearch1' if fonte == 'soundcloud' else 'ytsearch1'}:{texto}"
        opcoes = opcoes_ytdl(extract_flat="in_playlist")

    with yt_dlp.YoutubeDL(opcoes) as ydl:
        info = ydl.extract_info(alvo, download=False)
    if not info:
        return []
    entradas = info.get("entries")
    if entradas is None:
        entradas = [info]
    faixas = []
    for entrada in list(entradas)[:LIMITE_PLAYLIST]:
        if entrada:
            faixa = faixa_de_info(entrada, pedido_por)
            if faixa:
                faixas.append(faixa)
    return faixas


def buscar_parecida_soundcloud(titulo: str, pedido_por: int) -> Optional[Faixa]:
    """Procura no SoundCloud a mesma música, tentando o título limpo e depois o original."""
    tentativas = []
    for consulta in (limpar_titulo(titulo), titulo):
        if consulta not in tentativas:
            tentativas.append(consulta)
    for consulta in tentativas:
        try:
            achadas = buscar(consulta, "soundcloud", pedido_por)
        except Exception as erro:
            log.warning("Busca no SoundCloud falhou (%s): %s", consulta, erro)
            continue
        log.info("SoundCloud para '%s': %d resultado(s)", consulta, len(achadas))
        if achadas:
            return achadas[0]
    return None


def bloqueio_do_youtube(erro: Exception) -> bool:
    texto = str(erro).lower()
    return "sign in to confirm" in texto or "not a bot" in texto or "http error 429" in texto


def extrair_stream(faixa: Faixa) -> Faixa:
    """Pega o link de áudio de verdade (ele expira, por isso só na hora de tocar)."""
    import yt_dlp

    with yt_dlp.YoutubeDL(opcoes_ytdl()) as ydl:
        info = ydl.extract_info(faixa.pagina, download=False)
    if info.get("entries"):
        info = next(e for e in info["entries"] if e)
    faixa.stream = info.get("url")
    if not faixa.stream:
        raise RuntimeError("não encontrei o áudio dessa música")
    faixa.headers = dict(info.get("http_headers") or {})
    faixa.titulo = info.get("title") or faixa.titulo
    faixa.duracao = int(info["duration"]) if info.get("duration") else faixa.duracao
    faixa.thumb = info.get("thumbnail") or faixa.thumb
    return faixa
