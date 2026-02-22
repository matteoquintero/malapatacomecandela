# mpc/builders/playlist.py
# -*- coding: utf-8 -*-
"""
Construye listas de canciones desde Discogs + MusicBrainz + Backfill.
No llama APIs de YouTube ni OpenAI. No genera canciones ficticias.
"""

import logging
import random
from typing import List, Dict, Optional, Set

from mpc.utils.text import simp, key_pair
from mpc.catalog.genres import (
    GENRE_RULES, ANCHOR_ARTISTS, BACKFILL, DISCOGS_STYLE_MAP
)
import mpc.sources.musicbrainz as mb_client
import mpc.sources.discogs as dc_client

logger = logging.getLogger("mpc.builders.playlist")


def add_unique(rows: List[Dict], seen: Set[str], artist: str, title: str,
               source: str = "", query_override: str = "") -> bool:
    k = key_pair(artist, title)
    if k not in seen:
        rows.append({
            "artist": artist,
            "title": title,
            "query_override": query_override,
            "source": source,
        })
        seen.add(k)
        return True
    return False


def pick_playlist(
    discogs_client,
    genre: str,
    substyle: Optional[str],
    count: int,
) -> List[Dict]:
    """
    Construye una playlist para el género dado.
    Orden de fuentes: Discogs (prioridad) → MusicBrainz → Backfill canónico.
    substyle: 'underground' | 'comercial' | None
    """
    key = genre.lower().strip().replace("-", "_").replace(" ", "_")
    if key not in GENRE_RULES:
        logger.warning("Género '%s' no encontrado en GENRE_RULES, usando salsa_dura_clasica", key)
        key = "salsa_dura_clasica"

    rule = GENRE_RULES[key]
    anchors = ANCHOR_ARTISTS.get(key, [])
    anchor_set = {simp(a) for a in anchors}

    def is_anchor(artist: str) -> bool:
        return simp(artist) in anchor_set

    # 1) Discogs
    dc_base = dc_client.search_by_rule(discogs_client, key, DISCOGS_STYLE_MAP, rule, limit=180)
    dc_anch = dc_client.search_by_anchors(discogs_client, key, anchors, rule, limit_each=30) if anchors else []

    # 2) MusicBrainz
    mb_base = mb_client.search_by_rule(key, rule, limit=160)
    mb_anch = mb_client.search_by_anchors(key, rule, anchors, limit_each=30) if anchors else []

    logger.debug(
        "pick_playlist sources: dc_base=%d dc_anch=%d mb_base=%d mb_anch=%d",
        len(dc_base), len(dc_anch), len(mb_base), len(mb_anch),
    )

    pool = dc_base + dc_anch + mb_base + mb_anch

    # Dedupe
    seen: Set[str] = set()
    deduped: List[Dict] = []
    dc_set = set(id(x) for x in dc_base + dc_anch)
    for c in pool:
        artist, title = c.get("artist"), c.get("title")
        if not artist or not title:
            continue
        k = key_pair(artist, title)
        if k in seen:
            continue
        seen.add(k)
        src = c.get("source") or ("discogs" if id(c) in dc_set else "musicbrainz")
        deduped.append({"artist": artist, "title": title, "source": src})

    # Ordenar por substyle
    if substyle == "comercial":
        ordered = [c for c in deduped if is_anchor(c["artist"])] + \
                  [c for c in deduped if not is_anchor(c["artist"])]
    elif substyle == "underground":
        ordered = [c for c in deduped if not is_anchor(c["artist"])] + \
                  [c for c in deduped if is_anchor(c["artist"])]
    else:
        random.shuffle(deduped)
        ordered = deduped

    # Selección
    rows: List[Dict] = []
    used: Set[str] = set()
    for c in ordered:
        if len(rows) >= count:
            break
        add_unique(rows, used, c["artist"], c["title"], c.get("source", ""))

    # Backfill si faltan
    if len(rows) < count and key in BACKFILL:
        bfill = BACKFILL[key][:]
        if substyle == "underground":
            bfill.sort(key=lambda x: simp(x["artist"]) in anchor_set)
        else:
            bfill.sort(key=lambda x: simp(x["artist"]) not in anchor_set)
        for it in bfill:
            if len(rows) >= count:
                break
            add_unique(rows, used, it["artist"], it["title"], "backfill")

    # Último recurso genérico (MB)
    if len(rows) < count:
        gen = mb_client.mb_search_recordings('recording:"salsa" AND tag:"latin"', limit=120)
        for r in gen:
            if len(rows) >= count:
                break
            add_unique(rows, used, r["artist"], r["title"], "musicbrainz")

    logger.info("pick_playlist(%s): %d/%d canciones", key, len(rows), count)
    return rows[:count]


def pick_artist_playlist(
    discogs_client,
    artist: str,
    count: int,
    genre: Optional[str] = None,
) -> List[Dict]:
    """
    Construye una lista de canciones del artista dado.
    1) MusicBrainz recordings del artista
    2) Discogs backfill
    3) MB genérico por nombre
    """
    rows: List[Dict] = []
    seen: Set[str] = set()

    # 1) MB recordings del artista
    mb_tracks = mb_client.mb_search_recordings_by_artist(artist, limit=400)

    if genre:
        key = genre.lower().strip().replace("-", "_").replace(" ", "_")
        hints = GENRE_RULES.get(key, {}).get("query_hint", [])
        if hints:
            def score_g(item):
                txt = f"{item['artist']} {item['title']}".lower()
                return sum(1 for h in hints if h.lower() in txt)
            mb_tracks.sort(key=score_g, reverse=True)

    for r in mb_tracks:
        if len(rows) >= count:
            break
        add_unique(rows, seen, r["artist"], r["title"], "musicbrainz",
                   query_override=f'{artist} {r["title"]}')

    # 2) Discogs backfill
    if len(rows) < count:
        dc_tracks = dc_client.search_by_artist(discogs_client, artist, limit=200)
        for d in dc_tracks:
            if len(rows) >= count:
                break
            add_unique(rows, seen, d["artist"], d["title"], "discogs",
                       query_override=f'{artist} {d["title"]}')

    # 3) MB genérico filtrado por nombre
    if len(rows) < count:
        from mpc.sources.musicbrainz import _lucene_escape
        more = mb_client.mb_search_recordings(
            f'artist:"{_lucene_escape(artist)}" AND recording:*', limit=200
        )
        for r in more:
            if len(rows) >= count:
                break
            if simp(artist) not in simp(r["artist"]):
                continue
            add_unique(rows, seen, r["artist"], r["title"], "musicbrainz",
                       query_override=f'{artist} {r["title"]}')

    logger.info("pick_artist_playlist('%s'): %d/%d canciones", artist, len(rows), count)
    return rows[:count]
