# mpc/acquisition/steps/idempotency.py
# -*- coding: utf-8 -*-
"""
IdempotencyStep: evita descargas duplicadas consultando el repositorio.

Usa TrackRepository (BC Library) como fuente de verdad en vez del manifest CSV.
También chequea la librería en disco (lib_index) para el caso en que el archivo
exista pero no haya sido registrado todavía.
"""

import logging
import os
from typing import Any, Dict, Set

from mpc.acquisition.result import DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.library.repository import TrackRepository
from mpc.library.identity import track_id

logger = logging.getLogger("mpc.acquisition.steps.idempotency")


class IdempotencyStep(BaseStep):
    """
    Consulta TrackRepository y la librería en disco para evitar descargas duplicadas.
    Si la canción ya está registrada como 'downloaded' Y el archivo existe en disco,
    setea ctx['skip']=True. Si es un fantasma (BD downloaded pero sin archivo),
    continúa el pipeline para re-descargar.
    """

    def __init__(self, repository: TrackRepository, lib_index: Set[str], lib_base_dir: str = ""):
        self._repo = repository
        self._lib_index = lib_index
        self._lib_base_dir = lib_base_dir

    def run(self, ctx: Dict[str, Any]) -> None:
        req = ctx["request"]

        # Chequeo 1: repositorio + archivo en disco (fuente de verdad)
        track = self._repo.get(req.artist, req.title)
        if track and track.get("status") == "downloaded":
            fp = track.get("filepath") or ""
            curator_status = track.get("curator_status") or ""
            # Skip SOLO si el archivo realmente existe en disco.
            # Fantasmas (curator_status='missing' o filepath inválido) → re-descargar
            if fp and os.path.isfile(fp) and curator_status != "missing":
                ctx["skip"] = True
                ctx["skip_status"] = DownloadStatus.SKIPPED_MANIFEST
                ctx["skip_reason"] = "repositorio (artist-title ya descargado)"
                return
            # Si archivo no existe, loggear y continuar pipeline
            logger.info(
                "idempotency: fantasma detectado %s|%s status=downloaded pero sin archivo (%s) — re-descargando",
                req.artist, req.title, fp or "sin filepath",
            )

        # Chequeo 2: archivo físico en librería
        key = track_id(req.artist, req.title)
        if key in self._lib_index:
            # Buscar filepath real
            artist_norm, title_norm = key.split("|")
            filepath = self._find_filepath(artist_norm, title_norm)
            
            has_genre = track and track.get("genre_slug")
            is_existing = track and track.get("status") == "existing"
            
            #REGISTER en DB si está como "existing" O si no existe en DB
            if is_existing:
                self._repo.record(
                    artist=req.artist,
                    title=req.title,
                    status="downloaded",
                    filepath=filepath or "",
                )
                logger.info("idempotency: register (%s|%s) filepath=%s", req.artist, req.title, filepath)
            elif track is None:
                # Archivo en disco pero no en DB → agregar
                self._repo.record(
                    artist=req.artist,
                    title=req.title,
                    status="downloaded",
                    filepath=filepath or "",
                )
                logger.info("idempotency: new track from disk (%s|%s)", req.artist, req.title)
            
            # Guarda filepath en contexto para próximos steps
            if filepath:
                ctx["filepath"] = filepath
            
            # SOLO skip si tiene género (ya clasificado)
            # Si falta género → NO skip, el clasificador deduce
            if has_genre:
                ctx["skip"] = True
                ctx["skip_status"] = DownloadStatus.SKIPPED_EXISTS
                ctx["skip_reason"] = "archivo ya existe en librería"
            # else: continúa pipeline → clasificador deduce género

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _find_filepath(self, artist_norm: str, title_norm: str) -> str:
        """Busca el filepath real de un track en la librería."""
        import os
        from mpc.utils.text import simp_pipeline
        
        if not self._lib_base_dir or not os.path.exists(self._lib_base_dir):
            return ""
        
        # Construir el key objetivo
        target_key = f"{artist_norm}|{title_norm}"
        
        for root, dirs, files in os.walk(self._lib_base_dir):
            for fn in files:
                if fn.lower().endswith(".mp3"):
                    name = os.path.splitext(fn)[0]
                    # El nombre del archivo es "Artist - Title", convertir a key
                    a, sep, t = name.partition(" - ")
                    if t:
                        file_key = f"{simp_pipeline(a)}|{simp_pipeline(t)}"
                        if file_key == target_key:
                            return os.path.join(root, fn)
        return ""
