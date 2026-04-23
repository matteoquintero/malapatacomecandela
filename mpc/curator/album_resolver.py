# mpc/curator/album_resolver.py
# -*- coding: utf-8 -*-
"""
AlbumResolver: resuelve el nombre real del álbum para un track vía cadena
de fuentes: MusicBrainz → Discogs → OpenAI LLM → vacío.

Reemplaza la regla antigua `TALB == genre_slug`. Ahora TALB guarda álbumes
reales. El género sigue en TCON.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger("mpc.curator.album_resolver")


class AlbumResolver:
    """Resuelve album+year vía cadena MB → Discogs → LLM → vacío."""

    def __init__(
        self,
        openai_client=None,
        openai_model: str = "gpt-4o-mini",
        discogs_client=None,
        min_mb_score: int = 90,
        min_llm_confidence: float = 0.7,
    ):
        self.openai_client = openai_client
        self.openai_model = openai_model
        self.discogs_client = discogs_client
        self.min_mb_score = min_mb_score
        self.min_llm_confidence = min_llm_confidence

    def resolve(self, artist: str, title: str, mbid: str = "") -> dict:
        """Cadena MB → Discogs → LLM. Retorna dict estándar.

        Formato: {"album": str, "year": str, "source": str, "confidence": float}
        source ∈ {"mb_mbid", "mb_search", "discogs", "llm", "none"}
        """
        if mbid:
            r = self._from_mb_mbid(mbid)
            if r.get("album"):
                return r

        r = self._from_mb_search(artist, title)
        if r.get("album"):
            return r

        r = self._from_discogs(artist, title)
        if r.get("album"):
            return r

        r = self._from_llm(artist, title)
        if r.get("album") and r.get("confidence", 0) >= self.min_llm_confidence:
            return r

        return {"album": "", "year": "", "source": "none", "confidence": 0.0}

    def _from_mb_mbid(self, mbid: str) -> dict:
        try:
            from mpc.sources.musicbrainz import mb_get
            data = mb_get(f"recording/{mbid}", {"inc": "releases"})
            releases = data.get("releases", [])
            if releases:
                rel = releases[0]
                year = (rel.get("date") or "").split("-")[0]
                album = rel.get("title", "").strip()
                if album:
                    return {"album": album, "year": year,
                            "source": "mb_mbid", "confidence": 1.0}
        except Exception as e:
            logger.debug("mb_mbid falló: %s", e)
        return {}

    def _from_mb_search(self, artist: str, title: str) -> dict:
        try:
            from mpc.sources.musicbrainz import mb_get, _lucene_escape
            q = (
                f'artist:"{_lucene_escape(artist)}" '
                f'AND recording:"{_lucene_escape(title)}"'
            )
            data = mb_get("recording", {"query": q, "limit": 3})
            for rec in data.get("recordings", []):
                score = rec.get("score", 0)
                if score < self.min_mb_score:
                    continue
                releases = rec.get("releases", [])
                if not releases:
                    continue
                rel = releases[0]
                year = (rel.get("date") or "").split("-")[0]
                album = rel.get("title", "").strip()
                if album:
                    return {"album": album, "year": year,
                            "source": "mb_search",
                            "confidence": score / 100.0}
        except Exception as e:
            logger.debug("mb_search falló: %s", e)
        return {}

    def _from_discogs(self, artist: str, title: str) -> dict:
        if not self.discogs_client:
            return {}
        try:
            results = list(self.discogs_client.search(
                track=title, artist=artist, type="release"
            ))[:5]
            for r in results:
                t = getattr(r, "title", "") or ""
                if not t:
                    continue
                # Discogs titles: "Artist - Album"
                parts = t.split(" - ", 1)
                album = parts[-1].strip() if len(parts) > 1 else t.strip()
                year = str(getattr(r, "year", "") or "").strip()
                if album:
                    return {"album": album, "year": year,
                            "source": "discogs", "confidence": 0.8}
        except Exception as e:
            logger.debug("discogs falló: %s", e)
        return {}

    def _from_llm(self, artist: str, title: str) -> dict:
        if not self.openai_client:
            return {}
        prompt = (
            f'Para la canción "{artist}" - "{title}", responde SOLO en JSON:\n'
            '{"album": "nombre del álbum", "year": "YYYY", "confidence": 0.0-1.0}\n\n'
            "Reglas estrictas:\n"
            '- Si NO estás seguro, "album": "" y confidence < 0.5\n'
            "- NO inventes. Prefiere vacío antes que adivinar.\n"
            "- Si hay múltiples releases, elige el ORIGINAL (primer release).\n"
            "- confidence >= 0.85 SOLO si estás casi seguro.\n"
            "- year en formato YYYY (4 dígitos) o vacío."
        )
        try:
            r = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=150,
            )
            raw = r.choices[0].message.content or "{}"
            data = json.loads(raw)
            album = str(data.get("album") or "").strip()
            year = str(data.get("year") or "").strip()
            try:
                confidence = float(data.get("confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0.0
            return {"album": album, "year": year, "source": "llm",
                    "confidence": confidence}
        except Exception as e:
            logger.debug("llm falló: %s", e)
        return {}


def build_default_resolver():
    """Factory: construye AlbumResolver con clientes desde config."""
    from mpc.config import get_config
    cfg = get_config()
    openai_client = None
    discogs_client = None
    try:
        from mpc.sources.openai_source import get_openai_client
        openai_client, _ = get_openai_client(cfg.openai_api_key, cfg.openai_model)
    except Exception:
        pass
    try:
        from mpc.sources.discogs import get_discogs_client
        discogs_client = get_discogs_client(cfg.discogs_token)
    except Exception:
        pass
    return AlbumResolver(
        openai_client=openai_client,
        openai_model=cfg.openai_model or "gpt-4o-mini",
        discogs_client=discogs_client,
    )
