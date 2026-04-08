# mpc/discovery/strategies/discogs_style.py
# -*- coding: utf-8 -*-
"""
Estrategia 3 – Discogs Style Search.

Discogs tiene la taxonomía de estilos mejor curada para música latina.
Se priorizan singles porque:
  release title == song title → par artista-canción directo y fiable.
Los releases/álbumes se incluyen con menor confidence porque el título
es el del álbum, no de la canción (sin fetch de tracklist adicional).

Para ARTIST intent: búsqueda por nombre de artista en Discogs.
"""

import logging
from typing import List, Optional
from mpc.discovery.strategies.base import BaseStrategy
from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest, QueryIntent
from mpc.discovery import normalizer as norm

logger = logging.getLogger("mpc.discovery.strategy.discogs_style")

_CONF_SINGLE  = 0.85   # single: título del release = canción
_CONF_RELEASE = 0.55   # release/album: título puede ser del álbum
_MAX_PER_STYLE = 120


class DiscogsStyleStrategy(BaseStrategy):
    name = "discogs_style"

    def __init__(self, discogs_client):
        self.client = discogs_client

    def execute(self, request: SearchRequest) -> List[Candidate]:
        if not self.client:
            return []

        if request.intent == QueryIntent.GENRE:
            return self._genre_search(request)
        if request.intent == QueryIntent.ARTIST:
            return self._artist_search(request)
        return []

    # ── GENRE ─────────────────────────────────────────────────────────────────

    def _genre_search(self, request: SearchRequest) -> List[Candidate]:
        styles = norm.discogs_styles(request.genre_key or "")
        if not styles:
            return []

        candidates: List[Candidate] = []
        seen = set()

        for style in styles:
            # 1. Singles primero (calidad alta)
            singles = self._search(type="single", style=style)
            for c in singles:
                k = f"{c.artist}|{c.title}"
                if k not in seen:
                    seen.add(k)
                    candidates.append(c)
            if len(candidates) >= _MAX_PER_STYLE:
                break

            # 2. Releases/álbumes si aún faltan (calidad media)
            if len(candidates) < _MAX_PER_STYLE // 2:
                releases = self._search(type="release", style=style)
                for c in releases:
                    k = f"{c.artist}|{c.title}"
                    if k not in seen:
                        seen.add(k)
                        candidates.append(c)

        logger.info("[%s] %d candidatos para estilos %s", self.name, len(candidates), styles)
        return candidates

    def _search(self, type: str, style: str) -> List[Candidate]:
        try:
            rs = self.client.search(type=type, genre="Latin", style=style)
            results = list(rs.page(1))
        except Exception as e:
            logger.debug("[%s] error buscando style=%s type=%s: %s", self.name, style, type, e)
            return []

        candidates = []
        confidence = _CONF_SINGLE if type == "single" else _CONF_RELEASE
        for rel in results:
            pair = _parse_release(rel)
            if pair:
                candidates.append(Candidate(
                    artist=pair["artist"],
                    title=pair["title"],
                    source=f"{self.name}_{type}",
                    confidence=confidence,
                    year=_parse_year(getattr(rel, "year", None)),
                    country=getattr(rel, "country", None),
                    evidence=[f"discogs_style:{style}", f"type:{type}"],
                ))
        return candidates

    # ── ARTIST ────────────────────────────────────────────────────────────────

    def _artist_search(self, request: SearchRequest) -> List[Candidate]:
        if not request.artist:
            return []
        try:
            rs = self.client.search(type="release", artist=request.artist)
            results = list(rs.page(1))
        except Exception as e:
            logger.debug("[%s] error buscando artista '%s': %s", self.name, request.artist, e)
            return []

        candidates = []
        for rel in results:
            pair = _parse_release(rel)
            if pair:
                candidates.append(Candidate(
                    artist=pair["artist"],
                    title=pair["title"],
                    source=self.name,
                    confidence=_CONF_RELEASE,
                    year=_parse_year(getattr(rel, "year", None)),
                    evidence=[f"discogs_artist:{request.artist}"],
                ))
        return candidates


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_release(rel) -> Optional[dict]:
    try:
        title = getattr(rel, "title", None)
        if isinstance(title, str) and " - " in title:
            a, s = title.split(" - ", 1)
            a, s = a.strip(), s.strip()
            if a and s:
                return {"artist": a, "title": s}

        artists = getattr(rel, "artists", None)
        artist_name = None
        if artists:
            artist_name = getattr(artists[0], "name", None) or getattr(artists[0], "anv", None)
        if artist_name and title:
            return {"artist": str(artist_name).strip(" ,"), "title": str(title).strip()}
    except Exception:
        pass
    return None


def _parse_year(val) -> Optional[int]:
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None
