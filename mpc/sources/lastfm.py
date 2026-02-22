# mpc/sources/lastfm.py
# -*- coding: utf-8 -*-
"""
Cliente Last.fm tag.gettoptracks.
- Busca los tracks más populares de un tag (género).
- Cache JSON con TTL 7 días.
- API key opcional: sin key usa la pública (limit reducido).
"""

import logging
import requests
from typing import List, Dict

from mpc.utils.cache import JSONCache
from mpc.config import PROJECT_DIR

logger = logging.getLogger("mpc.sources.lastfm")

LFM_BASE = "https://ws.audioscrobbler.com/2.0/"
_LFM_PUBLIC_KEY = "43689e3f0ebc9c5a4cf7a8d44f04a86b"  # clave pública/anon de Last.fm

_lfm_cache = JSONCache(str(PROJECT_DIR / "cache" / "lfm_cache.json"), ttl_days=7)

# Mapeo de genre_key → lista de tags de Last.fm (de mayor a menor relevancia)
GENRE_TO_TAGS: Dict[str, List[str]] = {
    "son_cubano":               ["son cubano", "son"],
    "guajira_moderna":          ["guajira"],
    "guaracha":                 ["guaracha"],
    "rumba_guaguanco":          ["rumba", "guaguanco"],
    "afro_cuban_jazz_descarga": ["latin jazz", "afro-cuban jazz", "descarga"],
    "mambo":                    ["mambo"],
    "cha_cha_cha":              ["cha-cha-cha", "charanga"],
    "boogaloo":                 ["boogaloo"],
    "salsa_dura_clasica":       ["salsa", "fania"],
    "guaguanco_fusionado":      ["salsa", "rumba"],
    "exotica":                  ["exotica"],
    "latin_soul":               ["latin soul"],
    "plena_bomba":              ["plena", "bomba"],
    "salsa_romantica":          ["salsa romantica"],
    "timba":                    ["timba"],
    "salsa_dura_revival":       ["salsa dura", "salsa"],
    # géneros directos
    "balada":                   ["balada"],
    "house":                    ["house"],
    "nueva_trova":              ["nueva trova"],
    "techno":                   ["techno"],
    "cumbia":                   ["cumbia"],
}


def search_by_tag(api_key: str, tag: str, limit: int = 100) -> List[Dict]:
    """
    Devuelve los tracks más populares de un tag en Last.fm.
    Resultados cacheados 7 días.
    """
    key = api_key or _LFM_PUBLIC_KEY
    cache_key = JSONCache.make_key("lfm_tag", tag, limit)
    cached = _lfm_cache.get(cache_key)
    if cached is not None:
        logger.debug("LastFM cache HIT [%d]: %s", len(cached), tag)
        return cached

    params = {
        "method": "tag.gettoptracks",
        "tag": tag,
        "api_key": key,
        "format": "json",
        "limit": min(limit, 200),
        "page": 1,
    }

    try:
        r = requests.get(LFM_BASE, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("LastFM error buscando tag '%s': %s", tag, e)
        return []

    out: List[Dict] = []
    tracks = data.get("tracks", {}).get("track", [])
    for t in tracks:
        title = t.get("name", "")
        artist = (t.get("artist") or {}).get("name", "")
        if title and artist:
            out.append({"artist": artist, "title": title, "source": "lastfm"})

    _lfm_cache.set(cache_key, out)
    logger.debug("LastFM tag '%s': %d tracks", tag, len(out))
    return out


def search_by_genre(api_key: str, genre_key: str, limit: int = 100) -> List[Dict]:
    """
    Busca tracks para un genre_key usando sus tags de Last.fm.
    Consulta hasta 2 tags y mezcla resultados.
    """
    tags = GENRE_TO_TAGS.get(genre_key, [])
    if not tags:
        logger.debug("LastFM: sin tags para género '%s'", genre_key)
        return []

    out: List[Dict] = []
    seen: set = set()
    per_tag = max(limit, 50)

    for tag in tags[:2]:  # máximo 2 tags por género
        tracks = search_by_tag(api_key, tag, limit=per_tag)
        for t in tracks:
            k = f"{t['artist'].lower()}|{t['title'].lower()}"
            if k not in seen:
                seen.add(k)
                out.append(t)
        if len(out) >= limit:
            break

    logger.info("LastFM género '%s': %d tracks", genre_key, len(out))
    return out[:limit]
