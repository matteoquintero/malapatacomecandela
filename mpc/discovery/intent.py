# mpc/search/intent.py
# -*- coding: utf-8 -*-
"""
QueryIntent y SearchRequest.
Separa QUÉ quiere el usuario de CÓMO se ejecuta la búsqueda.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QueryIntent(Enum):
    ARTIST  = "artist"   # canciones de un artista concreto
    GENRE   = "genre"    # descubrir canciones de un género/subgénero
    TRACK   = "track"    # encontrar una canción específica
    SIMILAR = "similar"  # recomendaciones parecidas a una semilla


@dataclass
class SearchRequest:
    intent: QueryIntent

    # ── ARTIST ────────────────────────────────────────────────────────────────
    artist: Optional[str] = None

    # ── GENRE ─────────────────────────────────────────────────────────────────
    genre_key: Optional[str] = None     # ej. "cha_cha_cha"
    substyle: Optional[str] = None      # "underground" | "comercial"

    # ── TRACK ─────────────────────────────────────────────────────────────────
    title: Optional[str] = None

    # ── SIMILAR ───────────────────────────────────────────────────────────────
    seed_mbid: Optional[str] = None     # MBID de la grabación semilla
    seed_tags: List[str] = field(default_factory=list)

    # ── Común ─────────────────────────────────────────────────────────────────
    count: int = 10
