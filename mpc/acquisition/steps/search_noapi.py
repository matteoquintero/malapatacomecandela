# mpc/download/steps/search_noapi.py
# -*- coding: utf-8 -*-
"""
NoApiSearchStep: busca tracks usando yt-dlp sin consumir cuota de YouTube API.

Soporta cualquier fuente que yt-dlp entienda:
  - ytsearch  → YouTube
  - scsearch  → SoundCloud

Cada candidato incluye 'url', 'platform' y 'thumbnail_url' además de los
campos legacy (video_id, etc.) para compatibilidad con el scorer.
"""

import logging
import re
import subprocess
from typing import Any, Dict, List, Optional

from mpc.acquisition.result import DownloadError, DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.acquisition.track_ref import SOUNDCLOUD, YOUTUBE, infer_platform
from mpc.utils.text import simp_pipeline as _simp, title_similarity as _title_similarity

logger = logging.getLogger("mpc.acquisition.steps.search_noapi")

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_STDERR_YT_ID = re.compile(r"\[youtube\]\s+([A-Za-z0-9_-]{11}):")

# Plantilla yt-dlp: agrega webpage_url para capturar la URL real de cualquier plataforma
_PRINT_TEMPLATE = "%(id)s|||%(title)s|||%(uploader)s|||%(webpage_url)s"


def _youtube_thumbnail(video_id: str) -> str:
    return f"https://i3.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _candidate_from_parts(parts: List[str], rank: int) -> Optional[Dict]:
    """Parsea una línea de salida de yt-dlp y construye un candidato enriquecido."""
    if len(parts) < 3:
        return None

    display_id = parts[0].strip()
    title      = parts[1].strip()
    uploader   = parts[2].strip()
    url        = parts[3].strip() if len(parts) >= 4 else ""

    if not title:
        return None

    # Inferir plataforma y URL canónica
    platform = infer_platform(url) if url else YOUTUBE
    if platform == YOUTUBE and VIDEO_ID_RE.fullmatch(display_id):
        canonical_url = url or f"https://www.youtube.com/watch?v={display_id}"
        thumbnail_url = _youtube_thumbnail(display_id)
        video_id = display_id
    elif platform == SOUNDCLOUD:
        canonical_url = url
        thumbnail_url = ""
        video_id = display_id  # SoundCloud numeric ID (para logs)
    else:
        # Plataforma desconocida o URL directa
        canonical_url = url or display_id
        thumbnail_url = ""
        video_id = display_id

    return {
        # Campos multi-plataforma
        "url":          canonical_url,
        "platform":     platform,
        "display_id":   display_id,
        "thumbnail_url": thumbnail_url,
        # Campos legacy (scorer, manifest, result)
        "video_id":     video_id,
        "title":        title,
        "channel":      uploader,
        "channel_id":   "",
        "description":  "",
        "channel_title_full": uploader,
        "channel_desc": "",
        "channel_subs": 0,
        "_rank":        rank,
        "_noapi":       True,
    }


def _parse_yt_dlp_output(stdout: str, max_results: int) -> List[Dict]:
    items = []
    for line in stdout.strip().splitlines():
        parts = line.split("|||")
        c = _candidate_from_parts(parts, len(items) + 1)
        if c:
            items.append(c)
        if len(items) >= max_results:
            break
    return items


def _fetch_metadata_for_ids(ytdlp_bin: str, video_ids: List[str]) -> List[Dict]:
    """Metadata para YouTube video IDs extraídos de stderr (SABR workaround)."""
    items = []
    for i, vid in enumerate(video_ids):
        yt_url = f"https://www.youtube.com/watch?v={vid}"
        for extra in ([], ["--extractor-args", "youtube:formats=missing_pot"]):
            cmd = [ytdlp_bin, "--skip-download", "--print", _PRINT_TEMPLATE] + extra + [yt_url]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and "|||" in r.stdout:
                    parts = r.stdout.strip().split("|||")
                    c = _candidate_from_parts(parts, i + 1)
                    if c:
                        items.append(c)
                        break
            except Exception:
                pass
    return items


def _search_source(ytdlp_bin: str, query: str, max_results: int, source: str) -> List[Dict]:
    """Llama yt-dlp para una fuente. Retorna candidatos enriquecidos con url/platform."""
    cmd = [
        ytdlp_bin,
        f"{source}{max_results}:{query}",
        "--skip-download",
        "--print", _PRINT_TEMPLATE,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            return _parse_yt_dlp_output(result.stdout, max_results)

        # Fallback SABR: extraer YouTube video IDs de stderr
        ids = [m for m in _STDERR_YT_ID.findall(result.stderr) if VIDEO_ID_RE.fullmatch(m)]
        if ids:
            return _fetch_metadata_for_ids(ytdlp_bin, ids[:max_results])

    except subprocess.TimeoutExpired:
        logger.debug("search_noapi: timeout en %s para %r", source, query)
    except Exception as e:
        logger.debug("search_noapi: error en %s: %s", source, e)
    return []


class NoApiSearchStep(BaseStep):
    """
    Busca candidatos usando yt-dlp sin API key.

    Soporta ytsearch (YouTube) y scsearch (SoundCloud).
    Solo corre si ctx["candidates"] está vacío y no hay video_id/track resuelto.
    """

    def __init__(
        self,
        ytdlp_bin: str = "yt-dlp",
        sources: Optional[List[str]] = None,
        max_results: int = 5,
        min_title_sim: float = 0.35,
    ):
        self.ytdlp_bin = ytdlp_bin
        self.sources = sources or ["ytsearch", "scsearch"]
        self.max_results = max_results
        self.min_title_sim = min_title_sim

    def run(self, ctx: Dict[str, Any]) -> None:
        if ctx.get("skip") or ctx.get("track_ref"):
            return
        if ctx.get("candidates"):  # step anterior ya encontró algo
            return

        req = ctx["request"]
        query = f"{req.artist} {req.title}"

        for src in self.sources:
            if src not in ("ytsearch", "scsearch"):
                continue
            items = _search_source(self.ytdlp_bin, query, self.max_results, src)
            filtered = [
                it for it in items
                if _title_similarity(req.title, it["title"]) >= self.min_title_sim
            ]
            if filtered:
                ctx.setdefault("candidates", []).extend(filtered)
                logger.debug("search_noapi[%s]: %d candidatos (plataformas: %s)",
                             src, len(filtered),
                             list({c.get("platform") for c in filtered}))
                break

        if not ctx.get("candidates"):
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.NO_MATCH
            ctx["error"] = DownloadError.SEARCH_NO_RESULTS
            ctx["error_detail"] = f"sin resultados noapi para: {query}"


# Alias para backward compat con código que importe el nombre anterior
YouTubeNoApiSearchStep = NoApiSearchStep
