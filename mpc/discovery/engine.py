# mpc/discovery/engine.py
# -*- coding: utf-8 -*-
"""
SearchEngine: orquestador del motor de búsqueda (BC Discovery).

Responsabilidades:
  1. build_plan() → selecciona estrategias según el intent.
  2. execute()    → corre estrategias primarias, evalúa umbral de calidad,
                    activa fallback si hace falta, delega ranking al Ranker.
                    Retorna CandidateSet (salida estándar del contexto).

Plan de estrategias por intent:

  GENRE:
    Primarias (paralelas en I/O, serializadas en MB por rate limit):
      0. MBRecordingTagStrategy     — tag en recordings (rápido, cobertura media)
      1. MBArtistExpandStrategy     — artist tag → MBID → recordings (backbone)
      2. DiscogsStyleStrategy       — style filter en Discogs (alta precisión)
    Fallback premium (N+1, solo si umbral no alcanzado):
      3. MBReleaseTracklistStrategy — release tag → tracklist (lento, muy preciso)

  ARTIST:
    Primarias:
      0. MBArtistRecordingsStrategy — MBID → recordings (alta confianza)
      1. DiscogsStyleStrategy       — artist search en Discogs

  TRACK / SIMILAR: stubs extensibles.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional

from mpc.discovery.candidate import Candidate, CandidateSet
from mpc.discovery.intent import QueryIntent, SearchRequest
from mpc.discovery.ranker import rank
from mpc.discovery.strategies.base import BaseStrategy
from mpc.discovery.strategies.mb_recording_tags import MBRecordingTagStrategy
from mpc.discovery.strategies.mb_artist_expand import MBArtistExpandStrategy
from mpc.discovery.strategies.mb_release_tracklist import MBReleaseTracklistStrategy
from mpc.discovery.strategies.discogs_style import DiscogsStyleStrategy
from mpc.discovery.strategies.mb_artist_recordings import MBArtistRecordingsStrategy

logger = logging.getLogger("mpc.discovery.engine")


@dataclass
class SearchPlan:
    primary: List[BaseStrategy]
    fallback: List[BaseStrategy] = field(default_factory=list)
    # mínimo de candidatos con confidence ≥ threshold antes de activar fallback
    quality_threshold: int = 5
    confidence_floor: float = 0.65


class SearchEngine:
    def __init__(self, discogs_client=None):
        self.discogs_client = discogs_client

    # ── Plan builder ──────────────────────────────────────────────────────────

    def build_plan(self, request: SearchRequest) -> SearchPlan:
        if request.intent == QueryIntent.GENRE:
            return SearchPlan(
                primary=[
                    MBRecordingTagStrategy(),
                    MBArtistExpandStrategy(),
                    DiscogsStyleStrategy(self.discogs_client),
                ],
                fallback=[
                    MBReleaseTracklistStrategy(),
                ],
                quality_threshold=max(request.count // 2, 3),
                confidence_floor=0.65,
            )

        if request.intent == QueryIntent.ARTIST:
            return SearchPlan(
                primary=[
                    MBArtistRecordingsStrategy(),
                    DiscogsStyleStrategy(self.discogs_client),
                ],
                fallback=[],
                quality_threshold=1,
            )

        # TRACK / SIMILAR: stubs (extender en futuras iteraciones)
        return SearchPlan(primary=[], fallback=[])

    # ── Ejecución ─────────────────────────────────────────────────────────────

    def execute(self, request: SearchRequest) -> CandidateSet:
        """
        Ejecuta el plan de búsqueda y retorna un CandidateSet.
        La salida siempre tiene artist, title, confidence y evidence por candidato.
        """
        t0 = time.time()
        plan = self.build_plan(request)

        # Estrategias primarias en paralelo a nivel de I/O,
        # pero MB internamente está serializado por _mb_lock (1 req/s).
        candidates = self._run_parallel(plan.primary, request)
        strategy_used = "primary"

        # Evaluar si hace falta fallback
        quality = sum(1 for c in candidates if c.confidence >= plan.confidence_floor)
        if quality < plan.quality_threshold and plan.fallback:
            logger.info(
                "engine: solo %d/%d candidatos quality≥%.2f → activando fallback",
                quality, plan.quality_threshold, plan.confidence_floor,
            )
            fallback_candidates = self._run_parallel(plan.fallback, request)
            candidates.extend(fallback_candidates)
            strategy_used = "primary+fallback"

        ranked = rank(candidates, request)
        elapsed = time.time() - t0

        logger.info(
            "engine[%s/%s]: %d candidatos → %d finales en %.1fs",
            request.intent.value,
            request.genre_key or request.artist or "?",
            len(candidates), len(ranked), elapsed,
        )

        return CandidateSet(
            candidates=ranked,
            intent=request.intent.value,
            genre=request.genre_key,
            strategy_used=strategy_used,
            elapsed_sec=round(elapsed, 2),
        )

    def _run_parallel(self, strategies: List[BaseStrategy],
                      request: SearchRequest) -> List[Candidate]:
        if not strategies:
            return []

        all_candidates: List[Candidate] = []
        # max_workers=2 porque MB está rate-limitado internamente;
        # Discogs puede correr en paralelo con MB sin conflicto.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(s.execute, request): s for s in strategies}
            for future in as_completed(futures):
                strategy = futures[future]
                try:
                    result = future.result()
                    all_candidates.extend(result)
                    logger.debug("[%s] %d candidatos", strategy.name, len(result))
                except Exception as e:
                    logger.warning("[%s] error: %s", strategy.name, e)

        return all_candidates
