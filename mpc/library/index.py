# mpc/library/index.py
# -*- coding: utf-8 -*-
"""
LibraryIndex: consultas de alto nivel sobre el repositorio.

Abstrae las queries SQL detrás de una interfaz semántica útil para:
  - Saber qué falta descargar
  - Ver el estado de la colección
  - Obtener listas para reintento
"""

from typing import Any, Dict, List

from mpc.library.repository import TrackRepository


class LibraryIndex:
    """
    Fachada de consultas sobre TrackRepository.

    Uso:
        repo = TrackRepository("cache/library.db")
        idx = LibraryIndex(repo)
        idx.failed()    → tracks que fallaron
        idx.to_retry()  → tracks fallidos no en la colección
    """

    def __init__(self, repository: TrackRepository):
        self._repo = repository

    def failed(self) -> List[Dict[str, Any]]:
        """Tracks con status='failed'."""
        return self._repo.by_status("failed")

    def downloaded(self) -> List[Dict[str, Any]]:
        """Tracks con status='downloaded' (colección completa)."""
        return self._repo.by_status("downloaded")

    def to_retry(self) -> List[Dict[str, Any]]:
        """
        Tracks fallidos que no tienen una descarga exitosa (por mismo track_id).
        Listos para reintentar.
        """
        failed = self.failed()
        downloaded_keys = {r["track_id"] for r in self.downloaded()}
        return [r for r in failed if r["track_id"] not in downloaded_keys]

    def by_artist(self, artist: str) -> List[Dict[str, Any]]:
        """Tracks (any status) que coincidan con el artista."""
        return self._repo.by_artist(artist)

    def by_genre(self, genre_slug: str) -> List[Dict[str, Any]]:
        """Tracks descargados de un género específico."""
        return [r for r in self._repo.by_genre(genre_slug)
                if r["status"] == "downloaded"]

    def summary(self) -> Dict[str, int]:
        """Conteo por estado."""
        all_tracks = self._repo.get_all()
        counts: Dict[str, int] = {}
        for r in all_tracks:
            s = r.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts
