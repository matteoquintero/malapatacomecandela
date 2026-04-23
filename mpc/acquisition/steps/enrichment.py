# mpc/acquisition/steps/enrichment.py
# -*- coding: utf-8 -*-
"""
GenreEnrichmentStep (Capa C1).

Consulta MusicBrainz y Discogs para el par (artist, title) del ctx y extrae
tags/styles oficiales. Son señales de alta confianza que el classifier usa
como boost fuerte (+3.5 por match en heurística y evidencia en el prompt LLM).

Diseño:
  - NO bloqueante. Si falla (red, timeout, no-match), el pipeline continúa.
  - Cada intento registra enrichment_status en ctx: "hit" | "miss" | "error" | "disabled" | "skipped".
  - Usa infra existente: mpc.sources.musicbrainz.mb_get y discogs_client directo.

Setea en ctx:
  - ctx["mb_tags"]: List[str]
  - ctx["discogs_styles"]: List[str]
  - ctx["enrichment_status"]: str
"""

import logging
import os
from typing import Any, Dict, List, Optional

from mpc.acquisition.steps.base import BaseStep
from mpc.utils.text import simp_pipeline as _simp

logger = logging.getLogger("mpc.acquisition.steps.enrichment")


def _mb_lookup_tags(artist: str, title: str, limit: int = 5) -> List[str]:
    """Consulta MB recording con artist+title, devuelve nombres de tag del mejor match."""
    try:
        from mpc.sources.musicbrainz import mb_get, _lucene_escape
    except Exception as e:
        logger.debug("enrichment: mb import fail: %s", e)
        return []

    a = _lucene_escape(artist)
    t = _lucene_escape(title)
    query = f'artist:"{a}" AND recording:"{t}"'
    try:
        data = mb_get("recording", {"query": query, "limit": limit, "offset": 0})
    except Exception as e:
        logger.debug("enrichment: mb query error: %s", e)
        return []

    recordings = data.get("recordings") or []
    if not recordings:
        return []

    # Pick the best-scored recording; MB returns a `score` field 0-100
    recordings.sort(key=lambda r: int(r.get("score") or 0), reverse=True)
    best = recordings[0]
    if int(best.get("score") or 0) < 80:
        return []

    tags = best.get("tag-list") or []
    out = []
    for t in tags:
        name = (t.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _discogs_lookup_styles(client, artist: str, title: str, limit: int = 5) -> List[str]:
    """Consulta Discogs por 'artist title' y devuelve styles del mejor release."""
    if not client:
        return []
    try:
        results = client.search(f"{artist} {title}", type="release", per_page=limit)
        # results es paginable; traer primera página
        page = list(results.page(1)) if hasattr(results, "page") else list(results)[:limit]
    except Exception as e:
        logger.debug("enrichment: discogs search error: %s", e)
        return []

    styles: List[str] = []
    artist_simp = _simp(artist)
    title_simp = _simp(title)
    for rel in page[:limit]:
        try:
            rel_title = _simp(getattr(rel, "title", "") or "")
            if artist_simp and artist_simp not in rel_title:
                continue
            if title_simp and title_simp.split()[0] not in rel_title:
                continue
            styles_attr = getattr(rel, "styles", None) or []
            for s in styles_attr:
                if s and s not in styles:
                    styles.append(s)
        except Exception:
            continue
        if styles:
            break
    return styles


class GenreEnrichmentStep(BaseStep):
    """
    Enriquece ctx con tags (MusicBrainz) y styles (Discogs) del track.
    Siempre safe: cualquier fallo registra enrichment_status pero no bloquea.
    """

    def __init__(self, enabled: bool = True, discogs_client: Optional[Any] = None):
        self.enabled = enabled
        self.discogs_client = discogs_client

    def run(self, ctx: Dict[str, Any]) -> None:
        if ctx.get("skip"):
            return

        ctx.setdefault("mb_tags", [])
        ctx.setdefault("discogs_styles", [])

        if not self.enabled:
            ctx["enrichment_status"] = "disabled"
            return

        req = ctx["request"]
        # Si el request ya trae genre explícito, no hace falta enrichment.
        if getattr(req, "genre", None):
            ctx["enrichment_status"] = "skipped_csv_genre"
            return

        meta = ctx.get("best_meta") or {}
        artist = (meta.get("artist") or req.artist or "").strip()
        title = (meta.get("title") or req.title or "").strip()
        if not artist or not title:
            ctx["enrichment_status"] = "skipped_empty"
            return

        mb_tags: List[str] = []
        dg_styles: List[str] = []
        err = False
        try:
            mb_tags = _mb_lookup_tags(artist, title)
        except Exception as e:
            logger.debug("enrichment: mb unexpected error: %s", e)
            err = True

        try:
            dg_styles = _discogs_lookup_styles(self.discogs_client, artist, title)
        except Exception as e:
            logger.debug("enrichment: discogs unexpected error: %s", e)
            err = True

        ctx["mb_tags"] = mb_tags
        ctx["discogs_styles"] = dg_styles
        if mb_tags or dg_styles:
            ctx["enrichment_status"] = "hit"
        elif err:
            ctx["enrichment_status"] = "error"
        else:
            ctx["enrichment_status"] = "miss"

        logger.debug(
            "enrichment[%s]: mb=%s discogs=%s",
            ctx["enrichment_status"], mb_tags, dg_styles,
        )
