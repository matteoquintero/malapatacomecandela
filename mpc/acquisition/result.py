# mpc/download/result.py
# -*- coding: utf-8 -*-
"""
Taxonomía de resultados y errores del DownloadEngine.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


class DownloadStatus(str, Enum):
    DOWNLOADED      = "downloaded"
    SKIPPED_MANIFEST = "skipped(manifest)"
    SKIPPED_EXISTS  = "skipped(already_exists)"
    NO_MATCH        = "no_match"
    DOWNLOAD_ERROR  = "download_error"
    TAGGING_ERROR   = "tagging_error"
    DRY_RUN         = "skipped(dryrun)"
    SKIPPED_CSV_DUP = "skipped(csv_duplicate)"
    INVALID_GENRE   = "invalid_genre"


class DownloadError(str, Enum):
    """Taxonomía de errores — permite manejo diferenciado en el engine."""
    SEARCH_NO_RESULTS  = "search_no_results"     # No se encontró video
    SEARCH_NO_CANDIDATE = "search_no_candidate"  # Resultados pero ninguno pasa filtros
    DOWNLOAD_FAILED    = "download_failed"        # yt-dlp falló todas las estrategias
    TAGGING_FAILED     = "tagging_failed"         # ffmpeg falló (no bloquea flujo)
    RATE_LIMIT         = "rate_limit"             # Cuota agotada
    EXTERNAL_TOOL      = "external_tool_missing"  # yt-dlp/ffmpeg no disponible
    INVALID_GENRE      = "invalid_genre"          # Slug no existe en GENRE_DIR


@dataclass
class DownloadResult:
    artist: str
    title: str
    status: DownloadStatus

    video_id: str = ""
    platform: str = ""   # youtube | soundcloud | direct | ""
    genre_slug: str = ""
    confidence: float = 0.0
    rationale: str = ""
    filepath: str = ""
    query_used: str = ""   # query enviada a la búsqueda (para el log CSV)
    command: str = ""      # comando de género (dl-salsa-dura-clasica, etc.)

    error: Optional[DownloadError] = None
    error_detail: str = ""

    def to_csv_row(self) -> dict:
        return {
            "artist":          self.artist,
            "title":           self.title,
            "query_used":      self.query_used or f"{self.artist} {self.title}",
            "video_id":        self.video_id,
            "platform":        self.platform,
            "predicted_genre": self.genre_slug,
            "confidence":      self.confidence,
            "rationale":       self.rationale,
            "command":         self.command,
            "status":          self.status.value,
            "stderr_tail":     self.error_detail if self.error else "",
            "filepath_hint":   self.filepath,
        }
