# mpc/download/steps/classifier.py
# -*- coding: utf-8 -*-
"""
GenreClassifierStep: determina el género musical de un track.

Soporta tres modos (CLASSIFIER_MODE):
  HEURISTIC_ONLY  — rápido, sin OpenAI
  LLM_FALLBACK    — heurística si confianza >= umbral, LLM como fallback
  LLM_ONLY        — siempre consulta el LLM

Si ctx["request"].genre está seteado, lo usa directamente (sin clasificar).
Setea ctx["genre_slug"], ctx["confidence"], ctx["rationale"].
"""

import json
import logging
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from mpc.catalog.genres import ALL_SLUGS, GENRE_COMMAND, GENRE_DB
from mpc.acquisition.result import DownloadError, DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.utils.text import simp_pipeline as _simp, strip_accents as _strip_accents

logger = logging.getLogger("mpc.acquisition.steps.classifier")

# ── Heurística: derivar keywords/artistas/negativos desde GENRE_DB ────────────


def _norm_slug(s: str) -> str:
    s = _strip_accents(s or "").lower()
    s = s.replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", s)


def _build_heuristics():
    keywords: Dict[str, List[str]] = defaultdict(list)
    artists_hint: Dict[str, List[str]] = defaultdict(list)
    negative: Dict[str, List[str]] = defaultdict(list)
    for g in GENRE_DB:
        slug = _norm_slug(g["name"])
        kws: List[str] = []
        kws += [_simp(a) for a in g.get("aliases", [])]
        kws += [_simp(x) for x in g.get("rhythm_traits", [])]
        for lst in g.get("instrumentation", {}).values():
            kws += [_simp(x) for x in lst]
        kws += [_simp(x) for x in g.get("signature_tracks", [])]
        seen: set = set()
        dedup = []
        for w in kws:
            w = w.strip()
            if not w or len(w) < 3 or w in seen:
                continue
            seen.add(w)
            dedup.append(w)
        keywords[slug] = dedup
        artists_hint[slug] = [_simp(a) for a in g.get("artists_key", [])]
        negative[slug] = [_simp(x) for x in g.get("negative", [])]
    return dict(keywords), dict(artists_hint), dict(negative)


_KEYWORDS, _ARTISTS_HINT, _NEGATIVE = _build_heuristics()


def _softmax(scores: List[float]) -> List[float]:
    if not scores:
        return []
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    tot = sum(exps) or 1.0
    return [e / tot for e in exps]


def heuristic_classify(meta: Dict) -> Dict:
    """Retorna {slug, confidence, rationale, command}."""
    text = " ".join([
        (meta.get("title") or "").lower(),
        (meta.get("description") or "").lower(),
        (meta.get("channel") or "").lower(),
    ])
    artist_text = _simp(meta.get("artist") or "")

    scores: Dict[str, float] = defaultdict(float)
    reasons: Dict[str, List[str]] = defaultdict(list)

    for slug, words in _KEYWORDS.items():
        for w in words:
            if w and w in text:
                scores[slug] += 1.8
                reasons[slug].append(f"kw:{w}")

    for slug, arts in _ARTISTS_HINT.items():
        for a in arts:
            if a and (a in artist_text or a in text):
                scores[slug] += 2.2
                reasons[slug].append(f"artist:{a}")

    for slug, negs in _NEGATIVE.items():
        for n in negs:
            if n and n in text:
                scores[slug] -= 1.2

    if all(v == 0.0 for v in scores.values()):
        scores["salsa_dura_clasica"] = 0.1
        reasons["salsa_dura_clasica"].append("default:bias")

    top = sorted(ALL_SLUGS, key=lambda s: scores.get(s, 0.0), reverse=True)[:5]
    raw_scores = [scores.get(s, 0.0) for s in top]
    probs = _softmax(raw_scores)
    best_slug = top[0]
    conf = probs[0] if probs else 0.0

    return {
        "slug": best_slug,
        "confidence": round(conf, 3),
        "rationale": f"Heurística: {', '.join(reasons.get(best_slug, [])[:4])}",
        "command": GENRE_COMMAND.get(best_slug, ""),
    }


def llm_classify(meta: Dict, openai_client: Any, model: str, genres_ref: str) -> Dict:
    """LLM classify. Si no hay cliente disponible, retorna fallback."""
    if not openai_client:
        return {"slug": "salsa_dura_clasica", "confidence": 0.72, "rationale": "fallback sin OpenAI", "command": GENRE_COMMAND.get("salsa_dura_clasica", "")}

    slugs_csv = ", ".join(ALL_SLUGS)
    prompt = f"""Eres musicólogo experto en salsa y géneros afrolatinos. Clasifica EXACTAMENTE en uno de estos slugs: {slugs_csv}.

Caso:
Título: {meta.get('title', '')}
Artista: {meta.get('artist', '')}
Canal: {meta.get('channel', '')}
Descripción: {meta.get('description', '')}

Referencia de géneros (JSON):
{genres_ref}

Formato de salida (JSON estricto):
{{"slug": "...", "confidence": 0.0-1.0, "rationale": "2-4 frases"}}
""".strip()

    try:
        comp = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Eres musicólogo. Responde SOLO JSON válido."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        text = comp.choices[0].message.content.strip()
        data = json.loads(text)
        slug_raw = (data.get("slug") or "").strip()
        slug_norm = slug_raw.lower().replace("-", "_").replace(" ", "_")
        slug = slug_norm if slug_norm in GENRE_COMMAND else "salsa_dura_clasica"
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.7))))
        return {
            "slug": slug,
            "confidence": round(conf, 3),
            "rationale": (data.get("rationale") or "").strip(),
            "command": GENRE_COMMAND.get(slug, ""),
        }
    except Exception as e:
        logger.debug("llm_classify error: %s", e)
        return {"slug": "salsa_dura_clasica", "confidence": 0.7, "rationale": "fallback LLM error", "command": GENRE_COMMAND.get("salsa_dura_clasica", "")}


class GenreClassifierStep(BaseStep):
    """
    Clasifica el género del track usando ctx["best_meta"].
    Si ctx["request"].genre está seteado, lo usa sin clasificar.
    Setea ctx["genre_slug"], ctx["confidence"], ctx["rationale"].
    """

    LOW_CONF_THRESHOLD = 0.80

    def __init__(
        self,
        mode: str = "LLM_FALLBACK",
        openai_client: Optional[Any] = None,
        openai_model: str = "gpt-4o-mini",
        genres_ref: str = "",
    ):
        self.mode = mode
        self.openai_client = openai_client
        self.openai_model = openai_model
        self.genres_ref = genres_ref

    def run(self, ctx: Dict[str, Any]) -> None:
        if ctx.get("skip"):
            return

        req = ctx["request"]

        # Género ya conocido: validar y pasar directo
        if req.genre:
            slug = _norm_slug(req.genre)
            if slug not in GENRE_COMMAND:
                ctx["skip"] = True
                ctx["skip_status"] = DownloadStatus.INVALID_GENRE
                ctx["error"] = DownloadError.INVALID_GENRE
                ctx["error_detail"] = f"género desconocido: {req.genre} (normalizado: {slug})"
                return
            ctx["genre_slug"] = slug
            ctx["confidence"] = 1.0
            ctx["rationale"] = f"Género directo desde CSV: {req.genre}"
            return

        meta = ctx.get("best_meta") or {
            "title": req.title, "artist": req.artist,
            "description": "", "channel": "",
        }

        if self.mode == "HEURISTIC_ONLY":
            result = heuristic_classify(meta)
        elif self.mode == "LLM_ONLY":
            result = llm_classify(meta, self.openai_client, self.openai_model, self.genres_ref)
        else:  # LLM_FALLBACK (default)
            h = heuristic_classify(meta)
            if h["confidence"] >= self.LOW_CONF_THRESHOLD:
                result = h
            else:
                llm = llm_classify(meta, self.openai_client, self.openai_model, self.genres_ref)
                result = llm
                result["confidence"] = max(llm["confidence"], h["confidence"] + 0.05)

        ctx["genre_slug"] = result["slug"]
        ctx["confidence"] = result["confidence"]
        ctx["rationale"] = result["rationale"]
        logger.debug("classifier[%s]: %s (%.2f)", self.mode, result["slug"], result["confidence"])
