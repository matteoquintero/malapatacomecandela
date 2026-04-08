# mpc/discovery/strategies/mb_artist_recordings.py
# -*- coding: utf-8 -*-
"""
Estrategia – MusicBrainz Artist Recordings (intent ARTIST).

  1. Resuelve nombre → MBID (evita homónimos validando tags/país).
  2. Obtiene grabaciones del artista por MBID.
  3. Filtra live/remaster si no se pidió.

Cache:
  - artist name → MBID (TTL 7 días)
  - artist MBID → recordings (TTL 30 días)
"""

import logging
from typing import List, Optional
from mpc.discovery.strategies.base import BaseStrategy
from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest
import mpc.sources.musicbrainz as mb

logger = logging.getLogger("mpc.discovery.strategy.mb_artist_recordings")

_CONFIDENCE = 0.88
_MAX_RECS   = 200

_FILTER_KEYWORDS = {"live", "remaster", "remastered", "remix", "version",
                    "edit", "radio", "instrumental", "acoustic", "karaoke"}


class MBArtistRecordingsStrategy(BaseStrategy):
    name = "mb_artist_recordings"

    def execute(self, request: SearchRequest) -> List[Candidate]:
        if not request.artist:
            return []

        mbid = mb.mb_resolve_artist(request.artist)
        if not mbid:
            logger.info("[%s] no se pudo resolver MBID para '%s'", self.name, request.artist)
            return []

        logger.info("[%s] MBID=%s para '%s'", self.name, mbid, request.artist)
        recordings = mb.mb_get_artist_recordings(mbid, limit=_MAX_RECS)

        candidates = []
        for r in recordings:
            title = r.get("title", "")
            if not title:
                continue
            if _is_variant(title):
                continue
            candidates.append(Candidate(
                artist=request.artist,
                title=title,
                mbid=r.get("id"),
                source=self.name,
                confidence=_CONFIDENCE,
                year=_parse_year(r.get("first-release-date")),
                evidence=[f"artist_mbid:{mbid}"],
            ))

        logger.info("[%s] %d grabaciones para '%s'", self.name, len(candidates), request.artist)
        return candidates


def _is_variant(title: str) -> bool:
    tl = title.lower()
    return any(kw in tl for kw in _FILTER_KEYWORDS)


def _parse_year(val: Optional[str]) -> Optional[int]:
    try:
        return int(str(val)[:4]) if val else None
    except (ValueError, TypeError):
        return None
