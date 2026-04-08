# mpc/search/normalizer.py
# -*- coding: utf-8 -*-
"""
Normalización de género por fuente.

Principio: el mismo género tiene nombres distintos en cada API.
Este módulo es el diccionario único de traducción.
Nunca hardcodear canciones aquí, solo mapeos de nomenclatura.
"""

from typing import Dict, List, Optional, Tuple
from mpc.catalog.genres import GENRE_RULES, DISCOGS_STYLE_MAP


# Variantes extra de tags MB que no están en GENRE_RULES (por calidad de cobertura)
_MB_TAG_EXTRAS: Dict[str, List[str]] = {
    "cha_cha_cha":              ["cha cha cha", "chachachá"],
    "afro_cuban_jazz_descarga": ["afro-cuban jazz", "latin jazz", "afrocuban jazz"],
    "rumba_guaguanco":          ["guaguancó", "afrocuban"],
    "salsa_dura_clasica":       ["salsa dura", "nuyorican salsa", "salsa neoyorquina"],
    "salsa_dura_revival":       ["neo-salsa", "salsa dura revival"],
    "plena_bomba":              ["bomba y plena", "musica puertorriquena"],
    "latin_soul":               ["latin soul music", "nuyorican soul"],
    "guaguanco_fusionado":      ["salsa con rumba", "salsa rumba"],
}

# Metadata contextual por género: era y escena geográfica
# Usados por el ranker como señales de calidad
GENRE_META: Dict[str, Dict] = {
    "son_cubano":               {"era": (1920, 1960), "scenes": ["Cuba"]},
    "guajira_moderna":          {"era": (1930, 1975), "scenes": ["Cuba"]},
    "guaracha":                 {"era": (1930, 1970), "scenes": ["Cuba"]},
    "rumba_guaguanco":          {"era": (1930, 1990), "scenes": ["Cuba"]},
    "afro_cuban_jazz_descarga": {"era": (1940, 1970), "scenes": ["Cuba", "United States"]},
    "mambo":                    {"era": (1940, 1965), "scenes": ["Cuba", "United States", "Mexico"]},
    "cha_cha_cha":              {"era": (1950, 1975), "scenes": ["Cuba", "United States"]},
    "boogaloo":                 {"era": (1965, 1975), "scenes": ["United States"]},
    "salsa_dura_clasica":       {"era": (1965, 1985), "scenes": ["United States", "Puerto Rico", "Colombia"]},
    "guaguanco_fusionado":      {"era": (1970, 1990), "scenes": ["Cuba", "United States"]},
    "exotica":                  {"era": (1950, 1970), "scenes": ["United States"]},
    "latin_soul":               {"era": (1965, 1975), "scenes": ["United States"]},
    "plena_bomba":              {"era": (1920, 1995), "scenes": ["Puerto Rico"]},
    "salsa_romantica":          {"era": (1980, 2000), "scenes": ["United States", "Puerto Rico", "Colombia"]},
    "timba":                    {"era": (1985, 2015), "scenes": ["Cuba"]},
    "salsa_dura_revival":       {"era": (2000, 2026), "scenes": ["United States", "Colombia", "Spain"]},
    "balada":                   {"era": (1960, 2015), "scenes": []},
    "house":                    {"era": (1985, 2026), "scenes": ["United States"]},
    "nueva_trova":              {"era": (1965, 1995), "scenes": ["Cuba"]},
    "techno":                   {"era": (1985, 2026), "scenes": ["Germany", "United States"]},
    "cumbia":                   {"era": (1940, 2026), "scenes": ["Colombia", "Argentina"]},
}


def mb_tags(genre_key: str) -> List[str]:
    """Tags de MusicBrainz para el género (sin duplicados, orden preservado)."""
    base = GENRE_RULES.get(genre_key, {}).get("mb_tags", [])
    extras = _MB_TAG_EXTRAS.get(genre_key, [])
    seen = set()
    result = []
    for t in base + extras:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def discogs_styles(genre_key: str) -> List[str]:
    """Estilos Discogs para el género."""
    return DISCOGS_STYLE_MAP.get(genre_key, [])


def era(genre_key: str) -> Optional[Tuple[int, int]]:
    """Rango de años canónico del género."""
    return GENRE_META.get(genre_key, {}).get("era")


def scenes(genre_key: str) -> List[str]:
    """Países/escenas de origen del género."""
    return GENRE_META.get(genre_key, {}).get("scenes", [])


def mb_tags_query(genre_key: str) -> str:
    """Query Lucene para MusicBrainz: OR de todos los tags del género."""
    tags = mb_tags(genre_key)
    if not tags:
        return 'tag:"latin"'
    return "(" + " OR ".join(f'tag:"{t}"' for t in tags) + ")"
