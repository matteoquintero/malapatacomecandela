# mpc/library/identity.py
# -*- coding: utf-8 -*-
"""
TrackIdentity: identidad estable de una pista.

track_id() genera un fingerprint normalizado (artist|title) que se usa como
clave primaria en el repositorio. Si existen IDs externos (MBID, ISRC) estos
tienen prioridad para la identidad fuerte.
"""

import re
from dataclasses import dataclass
from typing import Optional

from mpc.utils.text import strip_accents


def _key(s: str) -> str:
    """
    Normalización ESTRICTA para track_id: elimina acentos, puntuación Y
    separadores (guiones, slashes, interrogaciones). Esto garantiza que un
    mismo track visual produzca siempre el mismo fingerprint sin importar
    cómo se haya escrito (con `/`, `-`, `?`, etc.).

    Ej:
      'Muerto / Merecumbe' → 'muerto merecumbe'
      'Muerto - Merecumbe' → 'muerto merecumbe'
      '¿Por qué?'          → 'por que'
    """
    s = strip_accents(s or "").lower().strip()
    # quita TODO lo que no sea letra/número/espacio (incluye -, /, ?, ¿, etc.)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def track_id(artist: str, title: str) -> str:
    """
    Fingerprint estable: key(artist)|key(title).
    Ignora diferencias de puntuación/separadores para evitar duplicados
    cuando un título se sanitiza (ej. `/` → ` - `).
    """
    return f"{_key(artist)}|{_key(title)}"


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
