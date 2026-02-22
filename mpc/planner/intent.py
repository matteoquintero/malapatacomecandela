# mpc/planner/intent.py
# -*- coding: utf-8 -*-
"""
Clasificación de intención del usuario: extrae count, artista, tipo de tarea,
y decide si el pedido es "simple" (MB/Discogs) o "complex" (LLM curatorial).
"""

import re
import logging
from typing import Dict, Optional

from mpc.utils.text import strip_accents, simp, extract_count
from mpc.catalog.genres import BLOCKED_ARTISTS, BLOCKED_GENRES, DIRECT_GENRES

logger = logging.getLogger("mpc.planner.intent")

# ── Patrones ──────────────────────────────────────────────────────────────────

COMPLEX_KEYWORDS = [
    r"\b(m[aá]s\s+famos[ao]s?|m[aá]s\s+escuchad[ao]s?|lo\s+m[aá]s\s+(famoso|popular)|top\s+\d+|mejores|greatest hits|con\s+m[aá]s\s+reproducciones)\b",
    r"\b(underground|lado\s*b|deep\s*cuts?|rar[ao]s?|poco\s+conocid[ao]s?|que\s+no\s+sean\s+hits?|sin\s+hits?|no\s+comercial(es)?)\b",
    r"\b(en\s+vivo|versi[oó]n\s+en\s+vivo|live|colaboraci[oó]n|featuring|feat\.?)\b",
    r"\b(entre\s+1[89]\d{2}\s+y\s+20\d{2}|d[eé]cada\s+de\s+los\s+\d{2}|\b19\d{2}\b|\b20\d{2}\b)\b",
    r"\b(idioma|en\s+espa[nñ]ol|en\s+ingl[eé]s)\b",
    r"\b(la\s+(m[aá]s\s+)?(iconic|ic[oó]nica|emblem[aá]tica|cl[aá]sica))\b",
]

ALBUM_PAT = re.compile(r"\b(al[bv]um|álbum|lp|disco)\b", re.I)
SINGLE_PAT = re.compile(r"\b(canci[oó]n|track|tema)\b", re.I)


def is_complex_request(user_text: str) -> bool:
    t = strip_accents(user_text.lower())
    return any(re.search(p, t, flags=re.I) for p in COMPLEX_KEYWORDS)


def _clean_artist_name(name: str) -> str:
    """Elimina palabras descriptivas que no son parte del nombre del artista."""
    if not name:
        return ""
    noise = {
        # descriptores de popularidad/temporalidad
        "ineditas", "inedita", "raras", "rara", "raros", "raro",
        "clasicas", "clasica", "clasicos", "clasico",
        "mejores", "mejor", "top", "hits", "hit",
        "underground", "comercial", "popular", "famosas", "famosos",
        "famosa", "famoso",
        "nuevas", "nueva", "nuevos", "nuevo", "viejas", "vieja", "viejos",
        "viejo", "tempranas", "temprana", "tempranos", "temprano",
        "tardias", "tardia", "tardios", "tardio", "temas", "tema",
        "canciones", "cancion",
        # vocabulario de géneros afrolatinos y directos
        "salsa", "dura", "brava", "romantica", "romantico", "erotica",
        "mambo", "son", "cubano", "cubana", "guaracha", "rumba",
        "guaguanco", "timba", "boogaloo", "plena", "bomba", "exotica",
        "jazz", "latin", "latina", "latino", "descarga", "guajira",
        "moderna", "moderno", "soul", "revival", "afro", "cuban",
        "cha", "montuno", "clave", "balada", "house", "techno",
        "cumbia", "trova",
    }
    words = name.split()
    cleaned = [w for w in words if re.sub(r"[^\w]", "", w.lower()) not in noise]
    return " ".join(cleaned)  # cadena vacía si todo era vocabulario de género


def _guess_artist_from_text(user_text: str) -> Optional[str]:
    """Heurística para detectar artista en el texto. Complementa al LLM."""
    t = user_text.strip()
    t_norm = strip_accents(t.lower())

    # entre comillas (soporta comillas rectas y curvas)
    m = re.search(r'["\'\u201c\u201d]\s*([^"\'\u201c\u201d]+?)\s*["\'\u201c\u201d]', t)
    if m:
        name = m.group(1).strip()
        if 3 <= len(name) <= 80:
            return name

    # "solo X", "de X" al final del string
    m = re.search(r"\b(?:solo|s[óo]lo|de)\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        cand_clean = _clean_artist_name(cand)
        if cand_clean and len(cand_clean) >= 3:
            return cand_clean

    # "canciones de X"
    m = re.search(r"canciones\s+de\s+([a-záéíóúñ][\w\s\.\-&']{2,80})", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        cand_clean = _clean_artist_name(cand)
        if cand_clean and len(cand_clean) >= 3:
            return cand_clean

    # "cancion de X" o "cancion X"
    for pat in [
        r"cancion\s+de\s+([a-záéíóúñ][\w\s\.\-&']{2,80})",
        r"cancion\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$",
        r"canciones\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$",
    ]:
        m = re.search(pat, t_norm, flags=re.I)
        if m:
            cand = t[m.start(1):m.end(1)].strip(" :")
            cand_clean = _clean_artist_name(cand)
            if cand_clean and len(cand_clean) >= 3:
                return cand_clean

    return None


def classify_request(user_text: str) -> Dict:
    """
    Devuelve:
      {
        "mode": "simple" | "complex",
        "kind": "playlist" | "album" | "single" | "artist_playlist",
        "count": int | None,
        "artist_hint": str | None,
        "album_hint": str | None,
        "title_hint": str | None,
      }
    """
    mode = "complex" if is_complex_request(user_text) else "simple"
    kind = "playlist"
    artist_hint = _guess_artist_from_text(user_text)
    album_hint = None
    title_hint = None

    if ALBUM_PAT.search(user_text):
        kind = "album"

    if SINGLE_PAT.search(user_text):
        if extract_count(user_text) in (None, 1):
            kind = "single"

    if artist_hint and kind == "playlist":
        kind = "artist_playlist"

    return {
        "mode": mode,
        "kind": kind,
        "count": extract_count(user_text),
        "artist_hint": artist_hint,
        "album_hint": album_hint,
        "title_hint": title_hint,
    }


# ── Blocklist ─────────────────────────────────────────────────────────────────

def is_blocked(text: str) -> bool:
    """Devuelve True si el texto contiene artista o género bloqueado."""
    t = strip_accents(text.lower())
    return (
        any(a in t for a in BLOCKED_ARTISTS)
        or any(g in t for g in BLOCKED_GENRES)
    )


_BLOCKED_MESSAGES = [
    "🚫 {name} trae reggaetón barato. El portal de la candela no se abre con esa llave.",
    "🎭 {name}? Eso suena a reggaetón de baja frecuencia. Aquí solo vibra el eco de Lavoe y Colón.",
    "❌ {name} está vetado por los ancestros de la salsa. Trae guaguancó o no entres.",
    "🔥 {name} = reggaetón. Aquí solo se encienden discos que hacen sudar la clave.",
    "🎶 {name}? Pide a Fania, pide a la Ponceña, invoca calidad.",
    "🚫 {name}? Los dioses del mambo lo rechazaron. Aquí solo gira vinilo fino.",
    "🎵 {name} es reggaetón, pana. La candela pide Palmieri, Blades, Raphy Leavitt… no eso.",
    "❌ {name} no cruza este umbral. El reggaetón se queda afuera del templo de la clave.",
    "🔥 {name}? Eso es reggaetón. La máquina de fuego solo entiende salsa dura y son cubano.",
    "🎶 {name}? Bah. Aquí quemamos descargas y soneos, no ese plástico.",
]


def blocked_message(name: str) -> str:
    import random
    return random.choice(_BLOCKED_MESSAGES).format(name=name)


# ── Detectar género directo en el input ────────────────────────────────────────

def detect_direct_genre(user_input: str, genre_arg: Optional[str] = None) -> tuple:
    """
    Devuelve (instrucción, género_directo) o (user_input, None).
    genre_arg: valor del flag --genre si se usó en CLI.
    """
    if genre_arg:
        g = genre_arg.lower()
        if g in DIRECT_GENRES:
            return user_input, g
        # No es directo → lo trataremos como hint en el planner
        return user_input, None

    return user_input, None
