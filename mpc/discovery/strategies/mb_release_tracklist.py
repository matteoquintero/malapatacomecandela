# mpc/discovery/strategies/mb_release_tracklist.py
# -*- coding: utf-8 -*-
"""
Estrategia 2 – MusicBrainz Release Tracklist (fallback premium).

Solo se activa cuando las estrategias primarias no alcanzan el umbral
mínimo de calidad. Es más cara (N+1 calls) pero muy precisa.

Flujo:
  1. Buscar releases taggeados con el género.
  2. Para cada release: fetch tracklist (recordings + artist-credits).
  3. Devolver tracks reales de discos del género.

Cache:
  - release MBID → tracklist (TTL 30 días)

Rate limit: respetado por mb_get() (1 req/s).
Cold run para 15 releases ≈ 16 s. Warm ≈ 0.1 s.
"""

import logging
from typing import List, Optional
from mpc.discovery.strategies.base import BaseStrategy
from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest
from mpc.discovery import normalizer as norm
import mpc.sources.musicbrainz as mb

logger = logging.getLogger("mpc.discovery.strategy.mb_release_tracklist")

_MAX_RELEASES  = 15
_CONFIDENCE    = 0.80


class MBReleaseTracklistStrategy(BaseStrategy):
    name = "mb_release_tracklist"

    def execute(self, request: SearchRequest) -> List[Candidate]:
        if not request.genre_key:
            return []

        q = norm.mb_tags_query(request.genre_key)
        logger.debug("[%s] buscando releases: %s", self.name, q)

        releases = mb.mb_search_releases(q, limit=_MAX_RELEASES)
        if not releases:
            return []

        logger.info("[%s] %d releases para '%s'", self.name, len(releases), request.genre_key)

        candidates: List[Candidate] = []
        for rel in releases:
            release_mbid = rel.get("id")
            if not release_mbid:
                continue
            tracks = mb.mb_get_release_tracklist(release_mbid)
            for t in tracks:
                if not t.get("artist") or not t.get("title"):
                    continue
                candidates.append(Candidate(
                    artist=t["artist"],
                    title=t["title"],
                    mbid=t.get("mbid"),
                    source=self.name,
                    confidence=_CONFIDENCE,
                    year=_parse_year(rel.get("date")),
                    country=rel.get("country"),
                    evidence=[f"release_tag:{request.genre_key}"],
                ))

        logger.info("[%s] %d tracks totales", self.name, len(candidates))
        return candidates


def _parse_year(val: Optional[str]) -> Optional[int]:
    try:
        return int(str(val)[:4]) if val else None
    except (ValueError, TypeError):
        return None
