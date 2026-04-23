# mpc/download/steps/scorer.py
# -*- coding: utf-8 -*-
"""
CandidateScorerStep: elige el mejor candidato de la lista ctx["candidates"].

Extrae la lógica de choose_best_candidate() de pipeline_music.py.
Setea ctx["video_id"] y ctx["best_meta"] con el candidato elegido.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from mpc.acquisition.result import DownloadError, DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.acquisition.track_ref import TrackRef, ref_from_candidate
from mpc.utils.text import simp_pipeline as _simp, title_similarity as _title_sim

logger = logging.getLogger("mpc.acquisition.steps.scorer")

_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "y", "o", "u", "en", "con",
    "por", "para", "a", "al", "un", "una", "uno", "the", "of", "and", "feat", "ft",
}
_OFFICIAL_PAT = re.compile(r"\b(oficial|official)\b", re.I)
_TOPIC_PAT = re.compile(r"\b(topic|tema)\b", re.I)
_GENERIC_CH_PAT = re.compile(
    r"\b(salsa|radio|esquina|para todos|mix|hits|records|tv|canal|music channel)\b", re.I
)


def _extract_year(cand: Dict) -> Optional[int]:
    """Extrae año de lanzamiento desde release_year, release_date o upload_date (yt-dlp)."""
    for key in ("release_year", "release_date", "upload_date"):
        v = cand.get(key)
        if not v:
            continue
        s = str(v)
        m = re.search(r"(19|20)\d{2}", s)
        if m:
            try:
                year = int(m.group(0))
                if 1900 <= year <= 2100:
                    return year
            except ValueError:
                pass
    return None


def _key_tokens(title: str) -> set:
    return {t for t in _simp(title).split() if len(t) >= 4 and t not in _STOPWORDS}


def _best_abr(cand: Dict) -> float:
    """Extrae el mejor audio bitrate disponible del candidato. 0 si no hay info."""
    abr = cand.get("abr")
    if abr:
        try:
            return float(abr)
        except (TypeError, ValueError):
            pass
    formats = cand.get("formats") or []
    best = 0.0
    for f in formats:
        if not isinstance(f, dict):
            continue
        # Solo streams de audio (vcodec="none" en yt-dlp)
        if f.get("vcodec") and f.get("vcodec") != "none":
            continue
        a = f.get("abr") or 0
        try:
            a = float(a)
        except (TypeError, ValueError):
            a = 0
        if a > best:
            best = a
    return best


def _score_quality(cand: Dict) -> float:
    """Bonus/penalty por calidad de audio del mejor stream disponible.
    Aditivo al scoring existente (no reemplaza officiality/title/etc)."""
    abr = _best_abr(cand)
    if abr >= 256:
        return 1.5
    elif abr >= 192:
        return 1.0
    elif abr >= 128:
        return 0.5
    elif 0 < abr < 96:
        return -1.0
    return 0.0


def _score_officiality(artist: str, channel_title: str) -> float:
    a = _simp(artist)
    ch = _simp(channel_title)
    if not a or not ch:
        return 0.0
    score = 0.0
    if ch == a:
        score += 3.0
    if ch.startswith(a):
        score += 2.0
    if a in ch:
        score += 1.2
    if _OFFICIAL_PAT.search(ch):
        score += 2.5
    if _TOPIC_PAT.search(ch) and a in ch:
        score += 2.5
    if _GENERIC_CH_PAT.search(ch):
        score -= 1.0
    return score


def _has_artist_signal(artist: str, title: str, channel: str, desc: str) -> bool:
    a = _simp(artist)
    return a and (a in _simp(title) or a in _simp(channel) or a in _simp(desc))


def choose_best(candidates: List[Dict], artist: str, title: str) -> Optional[Dict]:
    """
    Filtra y puntúa candidatos; retorna el mejor o None.
    Lógica idéntica a choose_best_candidate() en pipeline_music.py.
    """
    if not candidates:
        return None

    MIN_TITLE_SIM = 0.62
    title_keys = _key_tokens(title)

    def _title_ok(cand_title: str) -> bool:
        sim = _title_sim(title, cand_title)
        cand_toks = set(_simp(cand_title).split())
        return sim >= MIN_TITLE_SIM and bool(title_keys & cand_toks)

    # Canal oficial: selección directa por vistas
    if any(c.get("_official_channel") for c in candidates):
        good = [c for c in candidates if _title_ok(c.get("title", ""))]
        if good:
            good.sort(key=lambda x: (int(x.get("views", 0)), -int(x.get("_rank", 9999))), reverse=True)
            return good[0]

    best, best_score = None, -1e9
    MIN_SCORE = 3.0

    for c in candidates:
        raw_title = c.get("title", "")
        ch = c.get("channel_title_full") or c.get("channel", "")
        desc = c.get("description", "") or ""
        dur = int(c.get("duration_sec") or 0)
        views = int(c.get("views") or 0)
        rank = int(c.get("_rank") or 9999)
        subs = int(c.get("channel_subs") or 0)
        from_noapi = bool(c.get("_noapi"))

        official_like = _score_officiality(artist, ch) >= 3.0 or ch.endswith(" - Topic")
        has_artist = _has_artist_signal(artist, raw_title, ch, desc)

        if not official_like and not has_artist:
            if from_noapi and _title_sim(title, raw_title) >= 0.75:
                pass
            else:
                logger.debug("scorer: descartado (sin artista) → %s | ch:%s", raw_title, ch)
                continue

        if not from_noapi and not _title_ok(raw_title):
            logger.debug("scorer: descartado (título bajo) → %s", raw_title)
            continue
        if from_noapi and _title_sim(title, raw_title) < 0.5:
            logger.debug("scorer: (noapi) descartado (sim baja) → %s", raw_title)
            continue

        score = 0.0
        score += _score_officiality(artist, ch) * 1.2
        score += _title_sim(title, raw_title) * 3.0
        if official_like:
            score += 2.5
        if from_noapi:
            score -= 0.5
        if views > 100_000:
            score += 1.0
        elif views > 10_000:
            score += 0.5
        if 150 <= dur <= 480:
            score += 0.5
        score -= rank * 0.1
        # NUEVO: bonus por calidad de audio (aditivo, no reemplaza otros filtros)
        score += _score_quality(c)

        if score > best_score:
            best_score = score
            best = c

    if best and best_score >= MIN_SCORE:
        return best
    return None


class CandidateScorerStep(BaseStep):
    """
    Elige el mejor candidato de ctx["candidates"] y setea ctx["video_id"] y ctx["best_meta"].
    Si no hay candidato válido, setea ctx["skip"]=True.
    """

    def run(self, ctx: Dict[str, Any]) -> None:
        if ctx.get("skip") or ctx.get("video_id"):
            return

        req = ctx["request"]
        candidates = ctx.get("candidates") or []

        best = choose_best(candidates, req.artist, req.title)
        if not best:
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.NO_MATCH
            ctx["error"] = DownloadError.SEARCH_NO_CANDIDATE
            ctx["error_detail"] = "ningún candidato pasó los filtros de artista/título"
            return

        ref = ref_from_candidate(best, image_type=getattr(req, "image_type", "hq"))
        ctx["track_ref"] = ref
        ctx["video_id"] = ref.display_id   # alias legacy para manifest/result
        ctx["best_meta"] = {
            "title": req.title,
            "artist": req.artist,
            "yt_title": best.get("title", ""),
            "description": best.get("description", ""),
            "channel": best.get("channel_title_full") or best.get("channel", ""),
            "duration_sec": int(best.get("duration_sec") or 0) or None,
            "release_year": _extract_year(best),
        }
        logger.debug("scorer: elegido platform=%s display_id=%s url=%s",
                     ref.platform, ref.display_id, ref.url)
