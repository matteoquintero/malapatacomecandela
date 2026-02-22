# mpc/sources/discogs.py
# -*- coding: utf-8 -*-
"""
Cliente Discogs. Requiere DISCOGS_TOKEN en .env.
"""

import logging
from typing import List, Dict, Optional

from mpc.utils.text import simp

logger = logging.getLogger("mpc.sources.discogs")


def get_discogs_client(token: str):
    """Crea y devuelve un cliente Discogs autenticado, o None si no está disponible."""
    if not token:
        return None
    try:
        import discogs_client
        client = discogs_client.Client(
            "mala-pata-come-candela/2.0 (mateoquintero)",
            user_token=token,
        )
        logger.debug("Discogs client OK")
        return client
    except ImportError:
        logger.warning("discogs_client no instalado (opcional). pip install discogs-client")
        return None
    except Exception as e:
        logger.warning("Error iniciando Discogs: %s", e)
        return None


def _discogs_release_to_pair(rel) -> Optional[Dict[str, str]]:
    try:
        t = getattr(rel, "title", None)
        if isinstance(t, str) and " - " in t:
            a, s = t.split(" - ", 1)
            a, s = a.strip(), s.strip()
            if a and s:
                return {"artist": a, "title": s, "source": "discogs"}
        artists = getattr(rel, "artists", None)
        name = None
        if artists:
            name = getattr(artists[0], "name", None) or getattr(artists[0], "anv", None)
        title = getattr(rel, "title", None)
        if name and title:
            return {"artist": str(name).strip(" ,"), "title": str(title).strip(), "source": "discogs"}
    except Exception:
        pass
    return None


def search_by_rule(client, key: str, style_map: Dict, rule: Dict, limit: int = 100) -> List[Dict]:
    if not client:
        return []
    out: List[Dict] = []
    styles = style_map.get(key, [])
    try:
        for st in styles:
            rs = client.search(type="release", genre="Latin", style=st)
            for rel in rs.page(1):
                pair = _discogs_release_to_pair(rel)
                if pair:
                    out.append(pair)
                if len(out) >= limit:
                    return out[:limit]
        if len(out) < limit:
            hints = " ".join(rule.get("query_hint", [])) or key.replace("_", " ")
            rs = client.search(type="release", genre="Latin", q=hints)
            for rel in rs.page(1):
                pair = _discogs_release_to_pair(rel)
                if pair:
                    out.append(pair)
                if len(out) >= limit:
                    break
        return out[:limit]
    except Exception as e:
        logger.debug("Discogs search_by_rule error: %s", e)
        return out[:limit]


def search_by_anchors(client, key: str, anchors: List[str], rule: Dict, limit_each: int = 30) -> List[Dict]:
    if not client or not anchors:
        return []
    out: List[Dict] = []
    try:
        for a in anchors:
            rs = client.search(type="release", genre="Latin", artist=a)
            count = 0
            for rel in rs.page(1):
                pair = _discogs_release_to_pair(rel)
                if pair:
                    out.append(pair)
                    count += 1
                if count >= limit_each:
                    break
        return out
    except Exception as e:
        logger.debug("Discogs search_by_anchors error: %s", e)
        return out


def search_by_artist(client, artist: str, limit: int = 120) -> List[Dict]:
    if not client:
        return []
    out: List[Dict] = []
    try:
        rs = client.search(type="release", artist=artist, genre="Latin")
        count = 0
        for rel in rs.page(1):
            pair = _discogs_release_to_pair(rel)
            if pair:
                if simp(artist).split()[0] not in simp(pair["artist"]):
                    continue
                out.append(pair)
                count += 1
            if count >= limit:
                break
        return out
    except Exception as e:
        logger.debug("Discogs search_by_artist error: %s", e)
        return out
