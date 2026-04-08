# mpc/discovery/strategies/mb_artist_expand.py
# -*- coding: utf-8 -*-
"""
Estrategia 1 – MusicBrainz Artist Expand (backbone de género).

Patrón: Semillas fuertes → Expansión → Canciones reales.

  1. Buscar artistas taggeados con el género en MusicBrainz.
     (Los artist-tags son mucho más ricos que los recording-tags.)
  2. Para cada artista → obtener sus grabaciones por MBID.
  3. Las grabaciones de artistas taggeados con ese género
     pertenecen con alta probabilidad a ese género.

Ventaja vs. búsqueda por nombre de canción:
  - Descubre canciones sin importar su título.
  - No mezcla géneros por coincidencia de texto.
  - Orgánico: no hardcodea artistas.

Cache:
  - genre → artist MBIDs (TTL 7 días)
  - artist MBID → recordings (TTL 30 días)

Rate limit: respetado por mb_get() con _mb_lock (1 req/s).
Cold run para 10 artistas ≈ 11 s. Warm run ≈ 0.1 s.
"""

import logging
from typing import List, Optional
from mpc.discovery.strategies.base import BaseStrategy
from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest
from mpc.discovery import normalizer as norm
import mpc.sources.musicbrainz as mb

logger = logging.getLogger("mpc.discovery.strategy.mb_artist_expand")

_MAX_ARTISTS   = 12   # artistas a expandir
_RECS_PER_ART  = 60   # grabaciones por artista
_CONFIDENCE    = 0.82  # mayor que recording_tags: artist tag es más fiable


class MBArtistExpandStrategy(BaseStrategy):
    name = "mb_artist_expand"

    def execute(self, request: SearchRequest) -> List[Candidate]:
        if not request.genre_key:
            return []

        # 1. Artistas taggeados con el género
        artists = mb.mb_search_artists(
            norm.mb_tags_query(request.genre_key),
            limit=_MAX_ARTISTS,
        )
        if not artists:
            logger.info("[%s] sin artistas para '%s'", self.name, request.genre_key)
            return []

        logger.info("[%s] %d artistas semilla para '%s'",
                    self.name, len(artists), request.genre_key)

        # 2. Expandir a grabaciones (secuencial, respeta rate limit MB)
        candidates: List[Candidate] = []
        for artist_data in artists:
            mbid = artist_data.get("id")
            name = artist_data.get("name", "")
            if not mbid or not name:
                continue

            recordings = mb.mb_get_artist_recordings(mbid, limit=_RECS_PER_ART)
            for r in recordings:
                title = r.get("title", "")
                if not title:
                    continue
                candidates.append(Candidate(
                    artist=name,
                    title=title,
                    mbid=r.get("id"),
                    source=self.name,
                    confidence=_CONFIDENCE,
                    year=_parse_year(r.get("first-release-date")),
                    evidence=[f"artist_tag:{request.genre_key}", f"artist:{name}"],
                ))

        logger.info("[%s] %d candidatos totales", self.name, len(candidates))
        return candidates


def _parse_year(val: Optional[str]) -> Optional[int]:
    try:
        return int(str(val)[:4]) if val else None
    except (ValueError, TypeError):
        return None
