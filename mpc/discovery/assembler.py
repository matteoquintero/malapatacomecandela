# mpc/discovery/assembler.py
# -*- coding: utf-8 -*-
"""
Assembler: construye listas de canciones desde el SearchEngine.

Punto de salida del BC Discovery hacia el exterior (CLI, pipeline).
Convierte CandidateSet en filas CSV listas para canciones.csv.

Funciones:
  pick_playlist()         — género/substyle → lista de canciones
  pick_artist_playlist()  — artista → lista de canciones
  build_album_csv()       — álbum MusicBrainz → tracklist
"""

import logging
from typing import Dict, List, Optional

from mpc.discovery.engine import SearchEngine
from mpc.discovery.intent import QueryIntent, SearchRequest
from mpc.utils.text import key_pair
from mpc.sources.musicbrainz import mb_search_release, mb_release_tracks

logger = logging.getLogger("mpc.discovery.assembler")


def pick_playlist(
    discogs_client,
    genre: str,
    substyle: Optional[str],
    count: int,
) -> List[Dict]:
    """
    Construye una playlist para el género dado.
    Delega completamente al SearchEngine (GENRE intent).
    Retorna filas listas para canciones.csv.
    """
    engine = SearchEngine(discogs_client=discogs_client)
    request = SearchRequest(
        intent=QueryIntent.GENRE,
        genre_key=genre.lower().strip().replace("-", "_").replace(" ", "_"),
        substyle=substyle,
        count=count,
    )
    candidate_set = engine.execute(request)
    return candidate_set.to_csv_rows()


def pick_artist_playlist(
    discogs_client,
    artist: str,
    count: int,
    genre: Optional[str] = None,
) -> List[Dict]:
    """
    Construye una playlist para un artista específico.
    Delega al SearchEngine (ARTIST intent).
    Retorna filas listas para canciones.csv.
    """
    engine = SearchEngine(discogs_client=discogs_client)
    request = SearchRequest(
        intent=QueryIntent.ARTIST,
        artist=artist,
        genre_key=genre,
        count=count,
    )
    candidate_set = engine.execute(request)
    return candidate_set.to_csv_rows()


def build_album_csv(artist: str, album: str) -> List[Dict]:
    """
    Busca el álbum en MusicBrainz y devuelve sus tracks.
    Retorna [] si no se encuentra.
    Retorna filas listas para canciones.csv.
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
