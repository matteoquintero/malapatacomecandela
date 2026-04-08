# mpc/catalog/genre.py
# -*- coding: utf-8 -*-
"""
Genre: Value Object del dominio compartido.

Reglas de negocio encapsuladas:
  - Un genre_slug debe pertenecer a ALL_SLUGS (invariante en construcción).
  - Igualdad por slug (semántica de Value Object).
  - Inmutable (frozen=True).
  - Conoce su comando de descarga y directorio de librería.

Uso:
    g = Genre("salsa_dura_clasica")
    g.command          # "dl-salsa-dura-clasica"
    g.directory        # "salsa_dura_clasica"
    g.is_direct        # False
    Genre("reggaeton") # → ValueError
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from mpc.catalog.genres import ALL_SLUGS, DIRECT_GENRES, GENRE_COMMAND, GENRE_DIR
from mpc.utils.text import strip_accents


def _normalize_slug(raw: str) -> str:
    """Normaliza un string crudo a formato de slug: minúsculas, guiones→underscore."""
    s = strip_accents(raw or "").lower()
    s = s.replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", s)


@dataclass(frozen=True)
class Genre:
    """
    Value Object que representa un género musical válido del sistema.

    No puede construirse con un slug inválido: falla en __post_init__.
    Usa Genre.from_raw() para convertir strings no validados.
    """

    slug: str

    def __post_init__(self) -> None:
        if self.slug not in ALL_SLUGS:
            raise ValueError(
                f"Género desconocido: '{self.slug}'. "
                f"Opciones válidas: {', '.join(sorted(ALL_SLUGS))}"
            )

    @classmethod
    def from_raw(cls, raw: str) -> "Genre":
        """
        Intenta construir un Genre normalizando el input.
        Lanza ValueError si el slug normalizado no es válido.
        """
        return cls(_normalize_slug(raw))

    @classmethod
    def try_parse(cls, raw: str) -> Optional["Genre"]:
        """
        Como from_raw() pero retorna None si el slug no es válido.
        Útil cuando el input puede ser vacío o libre.
        """
        if not raw:
            return None
        try:
            return cls.from_raw(raw)
        except ValueError:
            return None

    # ── Propiedades de dominio ─────────────────────────────────────────────

    @property
    def command(self) -> str:
        """Comando de descarga asociado (dl-music-system.sh)."""
        return GENRE_COMMAND[self.slug]

    @property
    def directory(self) -> str:
        """Subdirectorio en la librería de música."""
        return GENRE_DIR[self.slug]

    @property
    def is_direct(self) -> bool:
        """True si es un género directo (no afrolatino, flujo simplificado)."""
        return self.slug in DIRECT_GENRES

    @property
    def is_afrolatino(self) -> bool:
        """True si es un género afrolatino (clasificador completo)."""
        return not self.is_direct

    # ── Representación ────────────────────────────────────────────────────

    def __str__(self) -> str:
        return self.slug

    def __repr__(self) -> str:
        return f"Genre({self.slug!r})"
