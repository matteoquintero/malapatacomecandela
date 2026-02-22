# mpc/sources/musicbrainz.py
# -*- coding: utf-8 -*-
"""
Cliente MusicBrainz.
- Rate-limit: 1 req/seg con threading.Lock (seguro en contexto paralelo).
- Cache JSON con TTL 7 días para búsquedas de grabaciones.
"""

import time
import threading
import logging
import requests
from typing import List, Dict, Optional

from mpc.utils.text import simp
from mpc.utils.cache import JSONCache
from mpc.config import PROJECT_DIR

logger = logging.getLogger("mpc.sources.musicbrainz")

MB_BASE = "https://musicbrainz.org/ws/2"
UA = {"User-Agent": "mala-pata-come-candela/2.0 (mateoquintero)"}

# ── Rate limit thread-safe ─────────────────────────────────────────────────────
_mb_lock = threading.Lock()
_mb_last_call: float = 0.0

# ── Cache de búsquedas de grabaciones (TTL 7 días) ────────────────────────────
_mb_cache = JSONCache(str(PROJECT_DIR / "cache" / "mb_search_cache.json"), ttl_days=7)


def mb_get(path: str, params: Dict) -> Dict:
    """GET a MusicBrainz con rate-limit de 1 req/seg, thread-safe."""
    global _mb_last_call
    params = {**params, "fmt": "json"}
    with _mb_lock:
        elapsed = time.time() - _mb_last_call
        if elapsed < 1.05:
            time.sleep(1.05 - elapsed)
        try:
            r = requests.get(f"{MB_BASE}/{path}", params=params, headers=UA, timeout=30)
            _mb_last_call = time.time()
            logger.debug("MB GET %s status=%s", path, r.status_code)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            _mb_last_call = time.time()
            logger.debug("MB GET error %s: %s", path, e)
            raise


def _lucene_escape(s: str) -> str:
    return (s or "").replace('"', r'\"').strip()


def mb_search_recordings(query: str, limit: int = 100) -> List[Dict]:
    """Busca grabaciones. Resultados cacheados 7 días por query+limit."""
    cache_key = JSONCache.make_key("recordings", query, limit)
    cached = _mb_cache.get(cache_key)
    if cached is not None:
        logger.debug("MB cache HIT [%d]: %.60s", len(cached), query)
        return cached

    try:
        data = mb_get("recording", {"query": query, "limit": limit, "offset": 0})
    except Exception:
        return []

    out: List[Dict] = []
    for it in data.get("recordings", []):
        title = it.get("title")
        ac = it.get("artist-credit", [])
        names: List[str] = []
        for c in ac:
            if isinstance(c, dict) and c.get("name"):
                names.append(c["name"])
            elif isinstance(c, str):
                names.append(c)
        artist = " & ".join(names) if names else ""
        if title and artist:
            out.append({"artist": artist, "title": title, "source": "musicbrainz"})

    _mb_cache.set(cache_key, out)
    return out


def mb_search_recordings_by_artist(artist: str, limit: int = 200) -> List[Dict]:
    """Busca grabaciones de un artista específico en MusicBrainz."""
    a = _lucene_escape(artist)
    queries = [
        f'artist:"{a}"',
        f'artistname:"{a}" AND recording:*',
    ]
    out: List[Dict] = []
    seen: set = set()
    for q in queries:
        rs = mb_search_recordings(q, limit=limit)
        for r in rs:
            if simp(artist).split()[0] not in simp(r["artist"]):
                if simp(artist) not in simp(r["artist"]):
                    continue
            k = f"{simp(r['artist'])}|{simp(r['title'])}"
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
    return out[:limit]


def search_by_rule(key: str, rule: Dict, limit: int = 120) -> List[Dict]:
    """
    Búsqueda de grabaciones por género usando dos estrategias complementarias:
    1. Tag-only: la más fiable — busca grabaciones etiquetadas con los tags del género.
    2. Título + tag: supplemento — busca grabaciones cuyo título contiene hints del género.
    Los query_hint describen el género musicalmente, NO son términos de título esperados.
    """
    tags = rule.get("mb_tags", [])
    tags_or = " OR ".join([f'tag:"{t}"' for t in tags]) if tags else 'tag:"latin"'

    out: List[Dict] = []
    seen: set = set()

    # 1. Tag-only (más fiable para género)
    for r in mb_search_recordings(f'({tags_or})', limit=limit):
        k = f"{simp(r['artist'])}|{simp(r['title'])}"
        if k not in seen:
            seen.add(k)
            out.append(r)

    # 2. Título con hints + tag como complemento si hacen falta más
    if len(out) < limit and rule.get("query_hint"):
        hints_or = " OR ".join([f'"{h}"' for h in rule["query_hint"]])
        q2 = f'recording:({hints_or}) AND ({tags_or})'
        for r in mb_search_recordings(q2, limit=limit):
            k = f"{simp(r['artist'])}|{simp(r['title'])}"
            if k not in seen:
                seen.add(k)
                out.append(r)

    return out[:limit]


def search_by_anchors(key: str, rule: Dict, anchors: List[str], limit_each: int = 40) -> List[Dict]:
    """Busca grabaciones de artistas ancla filtrando por tags del género."""
    tags = rule.get("mb_tags", [])
    tags_or = " OR ".join([f'tag:"{t}"' for t in tags]) if tags else 'tag:"latin"'
    out: List[Dict] = []
    for a in anchors:
        q = f'({tags_or}) AND artist:"{a}"'
        out.extend(mb_search_recordings(q, limit=limit_each))
    return out


def mb_search_release(artist: str, album: str) -> Optional[Dict]:
    """Devuelve el mejor release-group para (artist, album)."""
    a = _lucene_escape(artist)
    al = _lucene_escape(album)
    q = (
        f'artist:"{a}" AND (releasegroup:"{al}" OR release:"{al}") '
        f'AND primarytype:"album"'
    )
    try:
        data = mb_get("release-group", {"query": q, "limit": 5})
    except Exception:
        return None

    rgs = data.get("release-groups", [])
    if not rgs:
        return None

    from mpc.utils.text import strip_accents

    def score(rg):
        title = (rg.get("title") or "").lower()
        exact = 0 if strip_accents(title) == strip_accents(album).lower() else 1
        date = rg.get("first-release-date") or "9999"
        return (exact, date)

    rgs.sort(key=score)
    return rgs[0]


def mb_release_tracks(release_group_id: str) -> List[Dict]:
    """Obtiene los tracks de un release group."""
    try:
        data = mb_get("release", {
            "release-group": release_group_id,
            "inc": "artist-credits+recordings",
            "limit": 1,
        })
    except Exception:
        return []

    releases = data.get("releases", [])
    if not releases:
        return []

    rel_id = releases[0]["id"]
    try:
        rel_data = mb_get(f"release/{rel_id}", {"inc": "recordings+artist-credits"})
    except Exception:
        return []

    tracks: List[Dict] = []
    for medium in rel_data.get("media", []):
        for tr in medium.get("tracks", []):
            rec = tr.get("recording", {})
            title = rec.get("title") or tr.get("title") or ""
            ac = rec.get("artist-credit", [])
            names: List[str] = []
            for c in ac:
                if isinstance(c, dict) and c.get("name"):
                    names.append(c["name"])
                elif isinstance(c, str):
                    names.append(c)
            artist_name = " & ".join(names) if names else ""
            if title and artist_name:
                tracks.append({"artist": artist_name, "title": title})
    return tracks
