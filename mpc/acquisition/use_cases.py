# mpc/acquisition/use_cases.py
# -*- coding: utf-8 -*-
"""
Casos de uso del Bounded Context Acquisition (capa Application).

Cada use case orquesta el dominio sin contener lógica de negocio propia.

Uso:
    from mpc.acquisition.use_cases import DownloadTrackUseCase
    from mpc.acquisition.engine import DownloadEngine, DownloadConfig
    from mpc.acquisition.request import DownloadRequest

    config = DownloadConfig.from_env()
    engine = DownloadEngine(config)
    use_case = DownloadTrackUseCase(engine)
    result = use_case.execute(DownloadRequest(
        artist="Celia Cruz",
        title="Quimbara",
        genre="guaracha",
    ))
"""

import logging
from typing import List, Optional

from mpc.acquisition.engine import DownloadEngine
from mpc.acquisition.events import TrackDownloaded, TrackSkipped
from mpc.acquisition.request import DownloadRequest
from mpc.acquisition.result import DownloadResult, DownloadStatus

logger = logging.getLogger("mpc.acquisition.use_cases")


class DownloadTrackUseCase:
    """
    Caso de uso: descargar un track musical dado un DownloadRequest.

    Orquesta DownloadEngine y emite TrackDownloaded o TrackSkipped al terminar.
    """

    _SKIP_STATUSES = {
        DownloadStatus.SKIPPED_MANIFEST,
        DownloadStatus.SKIPPED_EXISTS,
        DownloadStatus.SKIPPED_CSV_DUP,
    }

    def __init__(
        self,
        engine: DownloadEngine,
        event_handler: Optional[object] = None,
    ) -> None:
        """
        Args:
            engine:        Motor de descarga (DownloadEngine).
            event_handler: Objeto opcional con método on_event(event).
        """
        self._engine = engine
        self._event_handler = event_handler

    def execute(self, request: DownloadRequest) -> DownloadResult:
        """
        Ejecuta la descarga del track.

        Returns:
            DownloadResult con el estado final de la operación.
        """
        result = self._engine.process(request)

        # Publicar evento de dominio
        event = self._build_event(result)
        logger.debug("event: %s", event)
        if event and self._event_handler and hasattr(self._event_handler, "on_event"):
            self._event_handler.on_event(event)

        return result

    def _build_event(self, result: DownloadResult):
        if result.status == DownloadStatus.DOWNLOADED:
            return TrackDownloaded(
                artist=result.artist,
                title=result.title,
                platform=result.platform or "",
                genre_slug=result.genre_slug or "",
                video_id=result.video_id or "",
                filepath=result.filepath or "",
                confidence=result.confidence or 0.0,
            )
        if result.status in self._SKIP_STATUSES:
            return TrackSkipped(
                artist=result.artist,
                title=result.title,
                reason=result.rationale or result.error_detail or result.status.value,
                skip_code=result.status.value,
            )
        return None


class DownloadBatchUseCase:
    """
    Caso de uso: descargar una lista de tracks desde un CSV.

    Delega todo en DownloadEngine.process_csv() y emite los mismos eventos
    que DownloadTrackUseCase para cada resultado.
    """

    def __init__(
        self,
        engine: DownloadEngine,
        event_handler: Optional[object] = None,
    ) -> None:
        self._engine = engine
        self._track_use_case = DownloadTrackUseCase(engine, event_handler)

    def execute_csv(
        self,
        input_csv: str,
        output_csv: str,
        dry_run: bool = False,
    ) -> List[DownloadResult]:
        """Procesa todos los tracks de un CSV y escribe el log de resultados."""
        return self._engine.process_csv(input_csv, output_csv, dry_run=dry_run)
