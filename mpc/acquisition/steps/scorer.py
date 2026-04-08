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


def _key_tokens(title: str) -> set:
    return {t for t in _simp(title).split() if len(t) >= 4 and t not in _STOPWORDS}


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
            "description": best.get("description", ""),
            "channel": best.get("channel_title_full") or best.get("channel", ""),
        }
        logger.debug("scorer: elegido platform=%s display_id=%s url=%s",
                     ref.platform, ref.display_id, ref.url)
