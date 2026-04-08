# mpc/discovery/dedup.py
# -*- coding: utf-8 -*-
"""
Deduplicación de candidatos.

Jerarquía de claves:
  1. MBID  → identidad fuerte, sin ambigüedad
  2. normalize(artist) + normalize(title) → identidad fuzzy

Normalización elimina:
  - feat / ft / featuring
  - (live), (remaster), (remix), (radio edit), etc.
  - acentos, puntuación, mayúsculas
"""

import re
import unicodedata
from typing import Dict, List

from mpc.discovery.candidate import Candidate


_FEAT_RE    = re.compile(r'\s+(feat|ft|featuring)\.?\s+.+$', re.I)
_PAREN_RE   = re.compile(
    r'\s*[\(\[]\s*(live|remaster(?:ed)?|remix|version|edit|radio|mono|stereo'
    r'|instrumental|acoustic|acústico|extended|original|single)\s*.*?[\)\]]',
    re.I,
)
_PUNCT_RE   = re.compile(r'[^\w\s]')
_SPACES_RE  = re.compile(r'\s+')


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize(s: str) -> str:
    s = _FEAT_RE.sub("", s)
    s = _PAREN_RE.sub("", s)
    s = _strip_accents(s.lower().strip())
    s = _PUNCT_RE.sub("", s)
    return _SPACES_RE.sub(" ", s).strip()


def dedup_key(c: Candidate) -> str:
    if c.mbid:
        return f"mbid:{c.mbid}"
    return f"{normalize(c.artist)}|{normalize(c.title)}"


def dedup(candidates: List[Candidate]) -> List[Candidate]:
    """
    Elimina duplicados respetando la jerarquía MBID > fuzzy.
    Cuando hay colisión, conserva el candidato con mayor confidence.
    También incrementa la confianza de candidatos que aparecen en múltiples fuentes.
    """
    # Contar ocurrencias por clave fuzzy (para cross-source bonus)
    fuzzy_counts: Dict[str, int] = {}
    for c in candidates:
        fk = f"{normalize(c.artist)}|{normalize(c.title)}"
        fuzzy_counts[fk] = fuzzy_counts.get(fk, 0) + 1

    seen: Dict[str, Candidate] = {}
    for c in candidates:
        # Bonus por presencia en múltiples fuentes (antes de dedup)
        fk = f"{normalize(c.artist)}|{normalize(c.title)}"
        if fuzzy_counts.get(fk, 0) > 1:
            c.confidence = min(c.confidence + 0.10, 1.0)
            if "multi-source" not in c.evidence:
                c.evidence.append("multi-source")

        key = dedup_key(c)
        if key not in seen or c.confidence > seen[key].confidence:
            seen[key] = c

    return list(seen.values())
