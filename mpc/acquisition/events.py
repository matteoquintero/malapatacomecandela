# mpc/acquisition/events.py
# -*- coding: utf-8 -*-
"""
Eventos de dominio del Bounded Context Acquisition.

Los eventos son registros inmutables de algo que ocurrió en el dominio.
Siguen la convención de nombrarse en pasado.

Uso:
    from mpc.acquisition.events import TrackDownloaded, TrackSkipped

    downloaded = TrackDownloaded(
        artist="Celia Cruz",
        title="Quimbara",
        platform="youtube",
        genre_slug="guaracha",
        video_id="dQw4w9WgXcQ",
    )
    skipped = TrackSkipped(
        artist="Celia Cruz",
        title="Quimbara",
        reason="repositorio (artist-title ya descargado)",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TrackDownloaded:
    """
    Se emite cuando DownloadEngine completa con éxito la descarga de un track.

    Permite que otros BCs (ej. Library) reaccionen al evento
    sin acoplar a DownloadEngine directamente.
    """

    artist: str
    title: str
    platform: str                    # "youtube" | "soundcloud" | "spotify"
    genre_slug: str
    video_id: str

    filepath: Optional[str] = None
    confidence: float = 0.0
    occurred_at: str = field(default_factory=_utcnow)

    def __str__(self) -> str:
        return (
            f"TrackDownloaded("
            f"{self.artist!r} – {self.title!r}, "
            f"platform={self.platform}, genre={self.genre_slug})"
        )


@dataclass(frozen=True)
class TrackSkipped:
    """
    Se emite cuando DownloadEngine omite un track (ya descargado o no encontrado).
    """

    artist: str
    title: str
    reason: str                       # legible para logging/observabilidad
    skip_code: Optional[str] = None   # DownloadStatus.value para sistemas que lo necesiten
    occurred_at: str = field(default_factory=_utcnow)

    def __str__(self) -> str:
        return (
            f"TrackSkipped("
            f"{self.artist!r} – {self.title!r}, "
            f"reason={self.reason!r})"
        )
