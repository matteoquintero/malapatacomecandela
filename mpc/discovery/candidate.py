# mpc/discovery/candidate.py
# -*- coding: utf-8 -*-
"""
Candidate y CandidateSet: unidades de resultado del Discovery context.

Candidate   — una sola canción candidata con señales de confianza.
CandidateSet — el conjunto estándar de salida del SearchEngine.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Candidate:
    artist: str
    title: str

    # Identidad fuerte (evita dedup fuzzy cuando existe)
    mbid: Optional[str] = None          # MusicBrainz recording ID
    isrc: Optional[str] = None

    # Procedencia
    source: str = ""                    # "mb_recording_tag", "mb_artist_expand", etc.
    confidence: float = 0.0             # 0.0 – 1.0

    # Señales para el ranker
    evidence: List[str] = field(default_factory=list)   # razones legibles
    year: Optional[int] = None
    country: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "artist": self.artist,
            "title": self.title,
            "source": self.source,
            "query_override": "",
        }


@dataclass
class CandidateSet:
    """
    Salida estándar del SearchEngine.

    Contiene la lista ordenada de candidatos más metadatos del proceso de
    descubrimiento (intent, géneros usados, estrategia activada, tiempo).
    """
    candidates: List[Candidate] = field(default_factory=list)

    # Metadatos del proceso
    intent: str = ""                    # "genre" | "artist" | "track" | "similar"
    genre: Optional[str] = None         # genre_key usado en la búsqueda
    strategy_used: str = ""             # "primary" | "primary+fallback"
    elapsed_sec: float = 0.0

    def best(self) -> Optional[Candidate]:
        """El candidato de mayor confianza."""
        return self.candidates[0] if self.candidates else None

    def to_csv_rows(self) -> List[Dict]:
        """Serializa para escritura en CSV (canciones.csv)."""
        return [c.to_dict() for c in self.candidates]

    def __len__(self) -> int:
        return len(self.candidates)

    def __iter__(self):
        return iter(self.candidates)
