# mpc/discovery/use_cases.py
# -*- coding: utf-8 -*-
"""
Casos de uso del Bounded Context Discovery (capa Application).

Cada use case orquesta el dominio sin contener lógica de negocio propia.
Sigue el patrón Command/Handler: recibe una intención, delega al dominio,
retorna el resultado.

Uso:
    from mpc.discovery.use_cases import DiscoverTracksUseCase
    from mpc.discovery.engine import SearchEngine
    from mpc.discovery.intent import SearchRequest, QueryIntent

    engine = SearchEngine(discogs_client=my_discogs)
    use_case = DiscoverTracksUseCase(engine)
    candidate_set = use_case.execute(SearchRequest(
        intent=QueryIntent.GENRE,
        genre_key="salsa_dura_clasica",
        count=20,
    ))
"""

import logging
from typing import Optional

from mpc.discovery.candidate import CandidateSet
from mpc.discovery.engine import SearchEngine
from mpc.discovery.events import CandidatesDiscovered
from mpc.discovery.intent import SearchRequest

logger = logging.getLogger("mpc.discovery.use_cases")


class DiscoverTracksUseCase:
    """
    Caso de uso: descubrir pistas musicales dado un intent de búsqueda.

    Orquesta SearchEngine y emite CandidatesDiscovered al terminar.
    En un sistema con un bus de eventos real, el evento se publicaría aquí.
    """

    def __init__(
        self,
        engine: SearchEngine,
        event_handler: Optional[object] = None,
    ) -> None:
        """
        Args:
            engine:        Motor de búsqueda (SearchEngine).
            event_handler: Objeto opcional con método on_event(event).
                           Permite conectar observers sin acoplar al bus.
        """
        self._engine = engine
        self._event_handler = event_handler

    def execute(self, request: SearchRequest) -> CandidateSet:
        """
        Ejecuta el descubrimiento de tracks para el intent dado.

        Returns:
            CandidateSet con candidatos ordenados por confianza.
        """
        candidate_set = self._engine.execute(request)

        # Publicar evento de dominio
        event = CandidatesDiscovered(
            intent=candidate_set.intent,
            genre=candidate_set.genre,
            count=len(candidate_set),
            strategy_used=candidate_set.strategy_used,
            elapsed_sec=candidate_set.elapsed_sec,
        )
        logger.debug("event: %s", event)
        if self._event_handler and hasattr(self._event_handler, "on_event"):
            self._event_handler.on_event(event)

        return candidate_set
