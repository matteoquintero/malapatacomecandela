# mpc/acquisition/steps/idempotency.py
# -*- coding: utf-8 -*-
"""
IdempotencyStep: evita descargas duplicadas consultando el repositorio.

Usa TrackRepository (BC Library) como fuente de verdad en vez del manifest CSV.
También chequea la librería en disco (lib_index) para el caso en que el archivo
exista pero no haya sido registrado todavía.
"""

import logging
from typing import Any, Dict, Set

from mpc.acquisition.result import DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.library.repository import TrackRepository
from mpc.library.identity import track_id

logger = logging.getLogger("mpc.acquisition.steps.idempotency")


class IdempotencyStep(BaseStep):
    """
    Consulta TrackRepository y la librería en disco para evitar descargas duplicadas.
    Si la canción ya está registrada como 'downloaded' o existe el archivo físico,
    setea ctx['skip']=True.
    """

    def __init__(self, repository: TrackRepository, lib_index: Set[str]):
        self._repo = repository
        self._lib_index = lib_index

    def run(self, ctx: Dict[str, Any]) -> None:
        req = ctx["request"]

        # Chequeo 1: repositorio (fuente de verdad)
        track = self._repo.get(req.artist, req.title)
        if track and track.get("status") == "downloaded":
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.SKIPPED_MANIFEST
            ctx["skip_reason"] = "repositorio (artist-title ya descargado)"
            return

        # Chequeo 2: archivo físico en librería (sin registro en repo)
        key = track_id(req.artist, req.title)
        if key in self._lib_index:
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.SKIPPED_EXISTS
            ctx["skip_reason"] = "archivo ya existe en librería"
