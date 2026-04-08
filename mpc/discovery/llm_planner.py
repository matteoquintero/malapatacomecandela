# mpc/discovery/llm_planner.py
# -*- coding: utf-8 -*-
"""
Planificador LLM: convierte lenguaje natural en un plan estructurado.
Tres prompts: simple, curator (complejo), y directo (género ya conocido).
"""

import re
import json
import logging
from typing import Dict, Optional

from mpc.utils.text import strip_accents, simp, extract_count
from mpc.discovery.planner import _guess_artist_from_text
from mpc.catalog.genres import AFROLATINO_SLUGS

logger = logging.getLogger("mpc.discovery.llm_planner")

_GENRE_LIST = ", ".join(AFROLATINO_SLUGS)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_SIMPLE = (
    "Eres un planificador musical experto en música afrolatina.\n"
    "Lee la instrucción del usuario y devuelve SOLO JSON (sin explicaciones) con este esquema exacto:\n"
    "{\n"
    '  "task": "album" | "playlist",\n'
    '  "count": <int or null>,\n'
    '  "genre": <string or null>,\n'
    '  "substyle": <"underground"|"comercial"|null>,\n'
    '  "artist": <string or null>,\n'
    '  "album": <string or null>\n'
    "}\n"
    "Reglas:\n"
    "- Si pide un álbum, task=\"album\" y completa artist/album.\n"
    "- Si pide canciones, task=\"playlist\". Si menciona un artista sin álbum: rellena artist y deja album=null.\n"
    "- Si no dice cuántas, usa 10.\n"
    "- substyle: detecta 'underground' vs 'comercial' por tono; si no hay pista, deja null.\n"
    f"- genre debe ser uno de: {_GENRE_LIST}. Si no hay género explícito, deja null.\n"
    "- Devuelve **JSON válido** y nada más."
)

SYSTEM_CURATOR = (
    "Eres un planificador musical experto en música afrolatina (salsa y afines). "
    "Analiza la solicitud y devuelve SOLO JSON (sin explicaciones) con este esquema:\n"
    "{\n"
    '  "task": "album" | "playlist" | "single",\n'
    '  "count": <int or null>,\n'
    '  "genre": <string or null>,\n'
    '  "substyle": <"underground"|"comercial"|null>,\n'
    '  "artist": <string or null>,\n'
    '  "album": <string or null>,\n'
    '  "title": <string or null>,\n'
    '  "constraints": {\n'
    '     "popularity": "famous" | "underground" | null,\n'
    '     "year_min": <int or null>,\n'
    '     "year_max": <int or null>,\n'
    '     "live": <true|false|null>,\n'
    '     "collab": <true|false|null>,\n'
    '     "language": <string or null>\n'
    "  }\n"
    "}\n"
    "Reglas:\n"
    "- 'top', 'más famosa', 'más escuchada' → constraints.popularity=\"famous\".\n"
    "- 'underground', 'lado B', 'deep cuts', 'sin hits' → constraints.popularity=\"underground\".\n"
    "- Si menciona años o décadas, setea year_min/year_max. Si no hay, deja null.\n"
    "- Si pide 1 sola canción significativa → task=\"single\".\n"
    "- Si menciona artista sin álbum → artist=<nombre> y album=null.\n"
    f"- genre: uno de {_GENRE_LIST}; si no es claro, null.\n"
    "- Devuelve JSON válido y nada más."
)

SYSTEM_DIRECT_GENRE_TPL = (
    "Eres un asistente de música. Devuelve SOLO JSON válido con este esquema:\n"
    "{{\n"
    '  "task": "album" | "playlist",\n'
    '  "count": <int or null>,\n'
    '  "genre": "{genre}",\n'
    '  "substyle": null,\n'
    '  "artist": <string or null>,\n'
    '  "album": <string or null>\n'
    "}}\n"
    "INSTRUCCIONES:\n"
    "- genre SIEMPRE \"{genre}\" (nunca cambies este valor)\n"
    "- Si pide un álbum, task=\"album\" y completa artist/album.\n"
    "- Si menciona un artista sin álbum → artist=<nombre> y album=null.\n"
    "- Si no dice cuántas, usa 10.\n"
    "- Devuelve ÚNICAMENTE el JSON, sin explicaciones."
)

# ── Plan por defecto ───────────────────────────────────────────────────────────

_DEFAULT_PLAN = {
    "task": "playlist", "count": 10, "genre": None,
    "substyle": None, "artist": None, "album": None,
    "title": None,
    "constraints": {
        "popularity": None, "year_min": None, "year_max": None,
        "live": None, "collab": None, "language": None,
    },
}


def _heuristic_plan(user_text: str) -> Dict:
    """Fallback cuando no hay OpenAI."""
    txt = user_text.lower()
    sub = (
        "underground" if any(w in txt for w in ["underground", "oscuro", "crudo", "rare", "deep"])
        else ("comercial" if any(w in txt for w in ["hit", "clásico", "clasico", "popular", "radio", "mainstream"])
              else None)
    )
    plan = {**_DEFAULT_PLAN, "substyle": sub}
    cnt = extract_count(user_text)
    if cnt:
        plan["count"] = cnt

    cand_artist = _guess_artist_from_text(user_text)
    if cand_artist:
        plan["artist"] = cand_artist

    g_txt = simp(user_text)
    for g in AFROLATINO_SLUGS:
        if simp(g.replace("_", " ")) in g_txt or simp(g) in g_txt:
            plan["genre"] = g
            break

    m = re.search(r'album\s+(["\'\u201c\u201d]?)(.+?)\1\s+de\s+(.+)$', strip_accents(user_text), flags=re.I)
    if m:
        plan["task"] = "album"
        plan["album"] = m.group(2).strip()
        plan["artist"] = m.group(3).strip()

    return plan


def llm_plan(
    client,
    model: str,
    user_text: str,
    direct_genre: Optional[str] = None,
    force_curator: bool = False,
) -> Dict:
    """
    Construye el plan desde el texto del usuario.
    - direct_genre: si se pasó --genre con un género directo
    - force_curator: fuerza el prompt curatorial (pedidos complejos)
    Devuelve siempre un plan válido con defaults sensatos.
    """
    if not client:
        return _heuristic_plan(user_text)

    if direct_genre:
        system = SYSTEM_DIRECT_GENRE_TPL.format(genre=direct_genre)
    elif force_curator:
        system = SYSTEM_CURATOR
    else:
        system = SYSTEM_SIMPLE

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
        )
        txt = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if m:
            txt = m.group(0)
        data = json.loads(txt)

        data.setdefault("task", "playlist")
        data.setdefault("count", 1 if data["task"] == "single" else 10)
        data.setdefault("genre", direct_genre)
        data.setdefault("substyle", None)
        data.setdefault("artist", None)
        data.setdefault("album", None)
        data.setdefault("title", None)
        data.setdefault("constraints", _DEFAULT_PLAN["constraints"].copy())

        cnt = extract_count(user_text)
        if cnt:
            data["count"] = cnt

        if not data.get("artist"):
            cand = _guess_artist_from_text(user_text)
            if cand:
                data["artist"] = cand

        logger.debug("Plan LLM: %s", data)
        return data

    except Exception as e:
        logger.warning("Error en llm_plan: %s — usando heurística", e)
        plan = _heuristic_plan(user_text)
        if direct_genre:
            plan["genre"] = direct_genre
        return plan
