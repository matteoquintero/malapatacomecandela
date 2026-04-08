# mpc/library/identity.py
# -*- coding: utf-8 -*-
"""
TrackIdentity: identidad estable de una pista.

track_id() genera un fingerprint normalizado (artist|title) que se usa como
clave primaria en el repositorio. Si existen IDs externos (MBID, ISRC) estos
tienen prioridad para la identidad fuerte.
"""

from dataclasses import dataclass
from typing import Optional

from mpc.utils.text import simp_pipeline as _simp


def track_id(artist: str, title: str) -> str:
    """
    Fingerprint estable: simp(artist)|simp(title).
    Usa la misma normalización que el resto del pipeline para consistencia.
    """
    return f"{_simp(artist)}|{_simp(title)}"


@dataclass
class TrackIdentity:
    """
    Identidad de un track con señales fuertes opcionales (MBID, ISRC).

    La jerarquía es:
      1. MBID  → identidad sin ambigüedad (MusicBrainz recording ID)
      2. ISRC  → identidad internacional (puede haber múltiples por grabación)
      3. track_id(artist, title) → fingerprint fuzzy normalizado (fallback)
    """
    artist: str
    title: str
    mbid: Optional[str] = None
    isrc: Optional[str] = None

    @property
    def id(self) -> str:
        """Clave canónica para el repositorio."""
        if self.mbid:
            return f"mbid:{self.mbid}"
        if self.isrc:
            return f"isrc:{self.isrc}"
        return track_id(self.artist, self.title)

    @property
    def fuzzy_key(self) -> str:
        """Clave fuzzy siempre disponible (artist|title normalizados)."""
        return track_id(self.artist, self.title)
