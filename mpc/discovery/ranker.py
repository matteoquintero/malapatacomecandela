# mpc/discovery/ranker.py
# -*- coding: utf-8 -*-
"""
Ranker: puntúa y ordena candidatos usando señales reales.

Señales fuertes (peso alto):
  - confidence base asignada por la estrategia
  - presencia en múltiples fuentes (cross-source bonus, manejado en dedup.py)

Señales medias (peso moderado):
  - año dentro de la era canónica del género

Señales débiles (peso bajo):
  - país/escena de origen

Substyle:
  - "underground" → penaliza artistas ancla
  - "comercial"   → bonifica artistas ancla

Nunca ordena por "llegó primero".
"""

import logging
from typing import List, Set

from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest, QueryIntent
from mpc.discovery import normalizer as norm
from mpc.discovery.dedup import dedup, normalize as dedup_normalize
from mpc.catalog.genres import ANCHOR_ARTISTS

logger = logging.getLogger("mpc.discovery.ranker")

_ERA_BONUS    = 0.12
_SCENE_BONUS  = 0.05
_ANCHOR_DELTA = 0.10   # ±10% por substyle


def _anchor_set(genre_key: str) -> Set[str]:
    anchors = ANCHOR_ARTISTS.get(genre_key, [])
    return {dedup_normalize(a) for a in anchors}


def _score(candidate: Candidate, request: SearchRequest, anchors: Set[str]) -> float:
    s = candidate.confidence

    # Era
    if request.genre_key and candidate.year:
        era = norm.era(request.genre_key)
        if era and era[0] <= candidate.year <= era[1]:
            s += _ERA_BONUS
            if "era_match" not in candidate.evidence:
                candidate.evidence.append("era_match")

    # Escena geográfica
    if request.genre_key and candidate.country:
        for scene in norm.scenes(request.genre_key):
            if scene.lower() in candidate.country.lower():
                s += _SCENE_BONUS
                break

    # Substyle
    artist_norm = dedup_normalize(candidate.artist)
    is_anchor = artist_norm in anchors
    if request.substyle == "underground" and is_anchor:
        s -= _ANCHOR_DELTA
    elif request.substyle == "comercial" and is_anchor:
        s += _ANCHOR_DELTA

    return min(s, 1.0)


def rank(candidates: List[Candidate], request: SearchRequest) -> List[Candidate]:
    """
    1. Deduplica
    2. Puntúa
    3. Ordena por score desc
    4. Corta a request.count
    """
    deduped = dedup(candidates)
    anchors = _anchor_set(request.genre_key or "") if request.intent == QueryIntent.GENRE else set()

    scored = [(c, _score(c, request, anchors)) for c in deduped]
    scored.sort(key=lambda x: -x[1])

    logger.debug("Ranker: %d candidatos → %d deduplicados → top %d",
                 len(candidates), len(deduped), request.count)

    return [c for c, _ in scored[: request.count]]
