# mpc/discovery/strategies/mb_recording_tags.py
# -*- coding: utf-8 -*-
"""
Estrategia 0 – MusicBrainz Recording Tag Search.

Busca grabaciones directamente por tag de género.
Rápida pero cobertura limitada: no todos los recordings están taggeados.
Útil para géneros bien representados (salsa, mambo, timba).
"""

import logging
from typing import List
from mpc.discovery.strategies.base import BaseStrategy
from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest
from mpc.discovery import normalizer as norm
import mpc.sources.musicbrainz as mb

logger = logging.getLogger("mpc.discovery.strategy.mb_recording_tags")

_CONFIDENCE = 0.72


class MBRecordingTagStrategy(BaseStrategy):
    name = "mb_recording_tags"

    def execute(self, request: SearchRequest) -> List[Candidate]:
        if not request.genre_key:
            return []

        q = norm.mb_tags_query(request.genre_key)
        logger.debug("[%s] query: %s", self.name, q)

        recordings = mb.mb_search_recordings(q, limit=150)
        candidates = []
        for r in recordings:
            artist = r.get("artist", "")
            title  = r.get("title", "")
            if not artist or not title:
                continue
            c = Candidate(
                artist=artist,
                title=title,
                mbid=r.get("mbid"),
                source=self.name,
                confidence=_CONFIDENCE,
                year=_parse_year(r.get("year")),
                evidence=[f"tag_match:{request.genre_key}"],
            )
            candidates.append(c)

        logger.info("[%s] %d candidatos para '%s'", self.name, len(candidates), request.genre_key)
        return candidates


def _parse_year(val) -> int | None:
    try:
        return int(str(val)[:4]) if val else None
    except (ValueError, TypeError):
        return None
