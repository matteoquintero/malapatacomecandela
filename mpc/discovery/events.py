# mpc/discovery/events.py
# -*- coding: utf-8 -*-
"""
Eventos de dominio del Bounded Context Discovery.

Los eventos son registros inmutables de algo que ocurrió en el dominio.
Siguen la convención de nombrarse en pasado (CandidatesDiscovered, etc.).

Uso:
    from mpc.discovery.events import CandidatesDiscovered
    event = CandidatesDiscovered(
        intent="genre",
        genre="salsa_dura_clasica",
        count=42,
        strategy_used="primary+fallback",
        elapsed_sec=3.7,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CandidatesDiscovered:
    """
    Se emite cuando SearchEngine termina su ejecución y retorna un CandidateSet.

    Permite que otros BCs (ej. Acquisition) reaccionen al descubrimiento
    sin acoplar a SearchEngine directamente.
    """

    intent: str                  # "genre" | "artist" | "track" | "similar"
    count: int                   # candidatos encontrados
    strategy_used: str           # "primary" | "primary+fallback"
    elapsed_sec: float

    genre: Optional[str] = None  # genre_key si intent==GENRE
    artist: Optional[str] = None # artista si intent==ARTIST
    occurred_at: str = field(default_factory=_utcnow)

    def __str__(self) -> str:
        subject = self.genre or self.artist or "?"
        return (
            f"CandidatesDiscovered("
            f"intent={self.intent}, subject={subject!r}, "
            f"count={self.count}, strategy={self.strategy_used}, "
            f"elapsed={self.elapsed_sec:.1f}s)"
        )
