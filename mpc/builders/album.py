# mpc/builders/album.py
# -*- coding: utf-8 -*-
"""Construye el tracklist de un álbum desde MusicBrainz."""

import logging
from typing import List, Dict

from mpc.utils.text import key_pair
from mpc.sources.musicbrainz import mb_search_release, mb_release_tracks

logger = logging.getLogger("mpc.builders.album")


def build_album_csv(artist: str, album: str) -> List[Dict]:
    """
    Busca el álbum en MusicBrainz y devuelve sus tracks.
    Devuelve [] si no se encuentra.
    """
    rg = mb_search_release(artist, album)
    if not rg:
        logger.info("build_album_csv: sin release-group para '%s' — '%s'", artist, album)
        return []

    logger.debug("build_album_csv: release-group id=%s title=%s", rg.get("id"), rg.get("title"))
    tracks = mb_release_tracks(rg["id"])
    logger.debug("build_album_csv: %d tracks encontrados", len(tracks))

    rows: List[Dict] = []
    seen: set = set()
    for t in tracks:
        k = key_pair(t["artist"], t["title"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({
            "artist": t["artist"],
            "title": t["title"],
            "query_override": f'{t["artist"]} {t["title"]} {album}',
            "source": "musicbrainz",
        })
    return rows
