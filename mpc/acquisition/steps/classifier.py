# mpc/acquisition/steps/classifier.py
# -*- coding: utf-8 -*-
"""
GenreClassifierStep: determina el género musical de un track.

Modos (CLASSIFIER_MODE):
  HEURISTIC_ONLY  — rápido, sin OpenAI
  LLM_FALLBACK    — heurística si confianza >= umbral, LLM como fallback
  LLM_ONLY        — siempre consulta el LLM

Señales heurísticas:
  - keywords (aliases + rhythm_traits + instrumentation + signature_tracks)
  - artistas ancla (artists_key)
  - negativos (penalty)
  - año de lanzamiento vs [year_from, year_to] del género (SUAVE, no bloqueante)
  - canales de YouTube conocidos (known_channels)
  - tags de MusicBrainz / styles de Discogs (cuando GenreEnrichmentStep corre antes)

Si ctx["request"].genre está seteado, lo usa directamente (sin clasificar).
Setea ctx["genre_slug"], ctx["confidence"], ctx["rationale"].
Todas las clasificaciones quedan loggeadas en cache/classifier_log.jsonl (D1).
"""

import json
import logging
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from mpc.catalog.genres import ALL_SLUGS, GENRE_COMMAND, GENRE_DB
from mpc.acquisition.result import DownloadError, DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.acquisition.classifier_log import log_classification
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
    years: Dict[str, Tuple[Optional[int], Optional[int]]] = {}
    channels: Dict[str, List[str]] = defaultdict(list)
    durations: Dict[str, Optional[Tuple[int, int]]] = {}
    for g in GENRE_DB:
        slug = g["slug"]  # A3: usar el slug explícito, no derivarlo del nombre
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
        years[slug] = (g.get("year_from"), g.get("year_to"))
        channels[slug] = [_simp(c) for c in g.get("known_channels", [])]
        durations[slug] = g.get("typical_duration_sec")
    return dict(keywords), dict(artists_hint), dict(negative), years, dict(channels), durations


_KEYWORDS, _ARTISTS_HINT, _NEGATIVE, _YEARS, _CHANNELS, _DURATIONS = _build_heuristics()


# ── C7: Hard includes (anchors) ───────────────────────────────────────────────
# Canales y artistas que fuerzan un slug con confianza muy alta, saltando LLM.
# Usar SOLO cuando la señal es inequívoca (p.ej. sello oficial, artista 1-género).
# Los strings pasan por _simp() (strip_accents + lower) antes de comparar.

_ANCHOR_CHANNELS: Dict[str, str] = {
    _simp("Fania Records"): "salsa_dura_clasica",
    _simp("Fania All Stars"): "salsa_dura_clasica",
    _simp("Fania Records Official"): "salsa_dura_clasica",
    _simp("Craft Recordings"): "salsa_dura_clasica",
    _simp("Egrem"): "son_cubano",
    _simp("EGREM Oficial"): "son_cubano",
    _simp("Discos Fuentes"): "cumbia_clasica",
}

_ANCHOR_ARTISTS: Dict[str, str] = {
    _simp("Arsenio Rodriguez"): "son_montuno",
    _simp("Miguelito Cuni"): "son_montuno",
    _simp("Trio Matamoros"): "son_cubano",
    _simp("Compay Segundo"): "son_cubano",
    _simp("Ibrahim Ferrer"): "son_cubano",
    _simp("Los Van Van"): "songo",
    _simp("NG La Banda"): "timba",
    _simp("Irakere"): "afro_cuban_jazz",
    _simp("Israel Cachao Lopez"): "descarga",
    _simp("Cachao"): "descarga",
    _simp("Totico"): "rumba_guaguanco",
    _simp("Los Munequitos de Matanzas"): "rumba_guaguanco",
    _simp("Cortijo y su Combo"): "bomba",
    _simp("Rafael Cortijo"): "bomba",
    _simp("Los Corraleros de Majagual"): "cumbia_clasica",
    _simp("Lisandro Meza"): "cumbia_clasica",
}


def _hard_anchor(meta: Dict) -> Optional[Dict]:
    """Si hay un anchor inequívoco por canal o artista, retorna resultado listo
    con confidence alta y salta LLM. None si no hay match."""
    artist_s = _simp(meta.get("artist") or "")
    channel_s = _simp(meta.get("channel") or "")

    # Canales primero (más precisos cuando hay match exacto-parcial)
    for anchor, slug in _ANCHOR_CHANNELS.items():
        if anchor and anchor in channel_s:
            return {
                "slug": slug,
                "confidence": 0.96,
                "rationale": f"anchor canal: '{anchor}' → {slug}",
                "command": GENRE_COMMAND.get(slug, ""),
                "anchor": f"channel:{anchor}",
            }

    for anchor, slug in _ANCHOR_ARTISTS.items():
        if anchor and anchor in artist_s:
            return {
                "slug": slug,
                "confidence": 0.95,
                "rationale": f"anchor artista: '{anchor}' → {slug}",
                "command": GENRE_COMMAND.get(slug, ""),
                "anchor": f"artist:{anchor}",
            }
    return None


# ── C3: Few-shot examples para el prompt del LLM ──────────────────────────────
_FEW_SHOT_EXAMPLES = """
Ejemplos resueltos:

1. Willie Colón - Aguanile (1971, canal: Fania Records)
   → salsa_dura_clasica
   Razón: Fania + década de 70s + arreglo de trombón característico.

2. La-33 - La Pantera Mambo (2007)
   → salsa_dura_revival
   Razón: agrupación bogotana post-2005 que retoma el sonido duro neoyorquino.

3. Arsenio Rodríguez - Dile a Catalina (1946)
   → son_montuno
   Razón: padre del son montuno moderno, formato de conjunto con tres y tumbadoras.

4. Cachao - Descarga Cubana (1957)
   → descarga
   Razón: improvisación instrumental estilo jam afrocubano, liderada por Cachao.

5. Ismael Rivera con Cortijo - El Bombón de Elena
   → bomba
   Razón: Rafael Cortijo + Ismael Rivera = dúo icónico de bomba puertorriqueña.

6. Mongo Santamaría - Afro Blue (1959)
   → afro_cuban_jazz
   Razón: jazz modal con percusión afrocubana, estándar del género.

7. Héctor Lavoe - El Cantante (1978)
   → salsa_dura_clasica
   Razón: Fania, años 70, voz líder con orquesta neoyorquina de salsa dura.
""".strip()

# Mapa tag/style (MB/Discogs) → slug canónico. Poblado desde GENRE_RULES.mb_tags
# y DISCOGS_STYLE_MAP para resolver enrichment tags a slugs del catálogo.
try:
    from mpc.catalog.genres import GENRE_RULES, DISCOGS_STYLE_MAP
    _TAG_TO_SLUG: Dict[str, str] = {}
    for _slug, _rule in GENRE_RULES.items():
        for _tag in _rule.get("mb_tags", []):
            _TAG_TO_SLUG.setdefault(_simp(_tag), _slug)
    for _slug, _styles in DISCOGS_STYLE_MAP.items():
        for _style in _styles:
            _TAG_TO_SLUG.setdefault(_simp(_style), _slug)
except ImportError:
    _TAG_TO_SLUG = {}


def _softmax(scores: List[float]) -> List[float]:
    if not scores:
        return []
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    tot = sum(exps) or 1.0
    return [e / tot for e in exps]


def _year_boost(year: Optional[int], slug: str) -> float:
    """Señal SUAVE de año: +0.9 si cae en rango, -0.6 si >5 años fuera de year_to."""
    if not year:
        return 0.0
    yf, yt = _YEARS.get(slug, (None, None))
    if yf is None:
        return 0.0
    if year < yf - 5:
        return -0.6
    if yt is not None and year > yt + 5:
        return -0.6
    if (yf <= year) and (yt is None or year <= yt):
        return 0.9
    # Dentro de la ventana de gracia de 5 años: neutro
    return 0.0


def _duration_boost(dur: Optional[int], slug: str) -> float:
    """Señal SUAVE de duración: +0.3 si cae en rango típico."""
    rng = _DURATIONS.get(slug)
    if not dur or not rng:
        return 0.0
    lo, hi = rng
    if lo <= dur <= hi:
        return 0.3
    return 0.0


def _tag_boost_from_enrichment(ctx_like: Dict, slug: str) -> Tuple[float, List[str]]:
    """Suma tags/styles (MB+Discogs) que resuelven a este slug. +3.5 por match."""
    boost = 0.0
    hits: List[str] = []
    for key in ("mb_tags", "discogs_styles"):
        for tag in ctx_like.get(key) or []:
            resolved = _TAG_TO_SLUG.get(_simp(tag))
            if resolved == slug:
                boost += 3.5
                hits.append(f"{key[:-1]}:{tag}")
    return boost, hits


def heuristic_classify(meta: Dict, enrichment: Optional[Dict] = None) -> Dict:
    """Retorna {slug, confidence, rationale, command, top3, signals}."""
    enrichment = enrichment or {}
    # A1: aplicar _simp() (strip_accents + lower) al texto fuente para que matchee
    # keywords con tildes/ñ.
    text = " ".join([
        _simp(meta.get("title") or ""),
        _simp(meta.get("description") or ""),
        _simp(meta.get("channel") or ""),
    ])
    artist_text = _simp(meta.get("artist") or "")
    channel_text = _simp(meta.get("channel") or "")
    release_year = meta.get("release_year")
    duration_sec = meta.get("duration_sec")

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

    # B1: año de lanzamiento como señal SUAVE
    if release_year:
        for slug in ALL_SLUGS:
            yb = _year_boost(release_year, slug)
            if yb:
                scores[slug] += yb
                if yb > 0:
                    reasons[slug].append(f"year:{release_year}")

    # B2: canal de YouTube conocido
    for slug, chans in _CHANNELS.items():
        for c in chans:
            if c and c in channel_text:
                scores[slug] += 2.5
                reasons[slug].append(f"channel:{c}")

    # B3: duración típica
    if duration_sec:
        for slug in ALL_SLUGS:
            db = _duration_boost(duration_sec, slug)
            if db:
                scores[slug] += db

    # C1: boost por tags de enrichment (MB/Discogs)
    for slug in ALL_SLUGS:
        tb, thits = _tag_boost_from_enrichment(enrichment, slug)
        if tb:
            scores[slug] += tb
            reasons[slug].extend(thits)

    # C2: artist memory prior (inyectado por el Step vía enrichment["artist_prior"])
    prior = (enrichment or {}).get("artist_prior")
    if prior:
        prior_slug, prior_n, prior_total = prior
        if prior_slug in ALL_SLUGS:
            scores[prior_slug] += 4.0
            reasons[prior_slug].append(f"artist_prior:{prior_n}/{prior_total}")

    # A2: sin sesgo por defecto. Si no hay señal, confidence=0.0 → LLM decide.
    has_signal = any(v != 0.0 for v in scores.values())

    top = sorted(ALL_SLUGS, key=lambda s: scores.get(s, 0.0), reverse=True)[:5]
    raw_scores = [scores.get(s, 0.0) for s in top]
    probs = _softmax(raw_scores) if has_signal else [0.0] * len(top)
    best_slug = top[0] if has_signal else ""
    conf = probs[0] if probs and has_signal else 0.0

    top3 = [(s, round(scores.get(s, 0.0), 3)) for s in top[:3]]

    return {
        "slug": best_slug,
        "confidence": round(conf, 3),
        "rationale": f"Heurística: {', '.join(reasons.get(best_slug, [])[:4])}" if best_slug else "Heurística: sin señal",
        "command": GENRE_COMMAND.get(best_slug, ""),
        "top3": top3,
        "signals": {
            "year": release_year,
            "duration_sec": duration_sec,
            "channel_hit": any(c in channel_text for chans in _CHANNELS.values() for c in chans if c),
            "mb_tags": enrichment.get("mb_tags", []),
            "discogs_styles": enrichment.get("discogs_styles", []),
        },
    }


def llm_classify(
    meta: Dict,
    openai_client: Any,
    model: str,
    genres_ref: str,
    enrichment: Optional[Dict] = None,
    cot: bool = False,
) -> Dict:
    """LLM classify. Si no hay cliente disponible, retorna fallback explícito."""
    if not openai_client:
        return {
            "slug": "",
            "confidence": 0.0,
            "rationale": "sin OpenAI: heurística sin señal",
            "command": "",
        }

    enrichment = enrichment or {}
    slugs_csv = ", ".join(ALL_SLUGS)
    year_line = f"\nAño (release/upload): {meta.get('release_year')}" if meta.get("release_year") else ""
    dur_line = f"\nDuración: {meta.get('duration_sec')}s" if meta.get("duration_sec") else ""
    mb = enrichment.get("mb_tags") or []
    dg = enrichment.get("discogs_styles") or []
    enrich_line = ""
    if mb or dg:
        enrich_line = f"\nSeñales externas: MusicBrainz tags={mb} | Discogs styles={dg}"

    cot_line = ""
    if cot:
        cot_line = (
            "\nRazonamiento paso a paso (zona de ambigüedad detectada):\n"
            "1. Lista los 3 slugs más probables y qué señal los apoya.\n"
            "2. Descarta uno con justificación.\n"
            "3. Elige entre los 2 finales. Pares frecuentemente ambiguos: "
            "salsa_dura_clasica vs salsa_dura_revival (año); son_cubano vs son_montuno "
            "(formato/época); bomba vs plena; afro_cuban_jazz vs descarga.\n"
        )
    prompt = f"""Eres musicólogo experto en salsa y géneros afrolatinos. Clasifica EXACTAMENTE en uno de estos slugs: {slugs_csv}.

{_FEW_SHOT_EXAMPLES}

Caso a clasificar:
Título: {meta.get('title', '')}
Artista: {meta.get('artist', '')}
Canal: {meta.get('channel', '')}
Descripción: {meta.get('description', '')}{year_line}{dur_line}{enrich_line}

Referencia de géneros (JSON):
{genres_ref}
{cot_line}
Criterios:
- El año es una señal SUAVE: salsa dura de los 70s → salsa_dura_clasica, de 2005+ → salsa_dura_revival.
  Pero un son cubano moderno sigue siendo son_cubano.
- Si las señales externas (MB/Discogs) apuntan a un género claro, úsalas como evidencia fuerte.
- Prefiere el slug más específico que el caso justifique.

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
            "raw": data,
        }
    except Exception as e:
        logger.debug("llm_classify error: %s", e)
        return {
            "slug": "salsa_dura_clasica",
            "confidence": 0.5,
            "rationale": f"fallback LLM error: {e}",
            "command": GENRE_COMMAND.get("salsa_dura_clasica", ""),
        }


class GenreClassifierStep(BaseStep):
    """
    Clasifica el género del track usando ctx["best_meta"] y ctx["mb_tags"]/["discogs_styles"].
    Si ctx["request"].genre está seteado, lo usa sin clasificar.
    Setea ctx["genre_slug"], ctx["confidence"], ctx["rationale"].
    Cada clasificación se loggea en cache/classifier_log.jsonl.
    """

    LOW_CONF_THRESHOLD = 0.80

    def __init__(
        self,
        mode: str = "LLM_FALLBACK",
        openai_client: Optional[Any] = None,
        openai_model: str = "gpt-4o-mini",
        genres_ref: str = "",
        repository: Optional[Any] = None,
    ):
        self.mode = mode
        self.openai_client = openai_client
        self.openai_model = openai_model
        self.genres_ref = genres_ref
        self.repository = repository

    # C2: artist memory prior
    ARTIST_PRIOR_MIN_COUNT = 3
    ARTIST_PRIOR_RATIO = 0.70
    ARTIST_PRIOR_BOOST = 4.0

    def _artist_prior(self, artist: str) -> Optional[Tuple[str, int, int]]:
        """Consulta memoria: si ≥3 tracks del mismo artista y ≥70% misma clase,
        retorna (slug, matching_count, total). None si no aplica."""
        if not self.repository or not artist:
            return None
        try:
            stats = self.repository.artist_genre_stats(artist)
        except Exception as e:
            logger.debug("artist_prior: repo error: %s", e)
            return None
        total = sum(stats.values())
        if total < self.ARTIST_PRIOR_MIN_COUNT:
            return None
        top_slug, top_n = max(stats.items(), key=lambda kv: kv[1])
        if top_n / total < self.ARTIST_PRIOR_RATIO:
            return None
        return (top_slug, top_n, total)

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
            log_classification({
                "artist": req.artist, "title": req.title,
                "source": "csv_direct", "final_slug": slug, "final_confidence": 1.0,
            })
            return

        meta = ctx.get("best_meta") or {
            "title": req.title, "artist": req.artist,
            "description": "", "channel": "",
            "duration_sec": None, "release_year": None,
        }
        enrichment = {
            "mb_tags": ctx.get("mb_tags") or [],
            "discogs_styles": ctx.get("discogs_styles") or [],
            "artist_prior": self._artist_prior(req.artist),
        }

        llm_called = False
        llm_result: Optional[Dict] = None
        anchor_hit: Optional[Dict] = None

        # C7: hard includes (anchors). Si hay canal/artista inequívoco, saltar LLM.
        anchor_hit = _hard_anchor(meta)
        if anchor_hit:
            h = heuristic_classify(meta, enrichment)  # solo para log
            result = {
                "slug": anchor_hit["slug"],
                "confidence": anchor_hit["confidence"],
                "rationale": anchor_hit["rationale"],
                "command": anchor_hit["command"],
            }
            ctx["genre_slug"] = result["slug"]
            ctx["confidence"] = result["confidence"]
            ctx["rationale"] = result["rationale"]
            log_classification({
                "artist": req.artist,
                "title": req.title,
                "channel": meta.get("channel"),
                "release_year": meta.get("release_year"),
                "duration_sec": meta.get("duration_sec"),
                "mode": "ANCHOR",
                "anchor": anchor_hit["anchor"],
                "mb_tags": enrichment["mb_tags"],
                "discogs_styles": enrichment["discogs_styles"],
                "enrichment_status": ctx.get("enrichment_status", "skipped"),
                "heuristic_top3": h.get("top3", []),
                "heuristic_confidence": h.get("confidence", 0.0),
                "llm_called": False,
                "final_slug": result["slug"],
                "final_confidence": result["confidence"],
                "final_rationale": result["rationale"],
            })
            logger.debug("classifier[ANCHOR]: %s (%.2f) via %s",
                         result["slug"], result["confidence"], anchor_hit["anchor"])
            return

        if self.mode == "HEURISTIC_ONLY":
            h = heuristic_classify(meta, enrichment)
            result = h
        elif self.mode == "LLM_ONLY":
            h = heuristic_classify(meta, enrichment)  # solo para top3 en log
            llm_result = llm_classify(meta, self.openai_client, self.openai_model, self.genres_ref, enrichment)
            llm_called = True
            result = llm_result
        else:  # LLM_FALLBACK (default)
            h = heuristic_classify(meta, enrichment)
            if h["confidence"] >= self.LOW_CONF_THRESHOLD and h["slug"]:
                result = h
            else:
                # C4: CoT si heurística cae en zona gris [0.40, 0.70)
                use_cot = 0.40 <= h["confidence"] < 0.70
                llm_result = llm_classify(
                    meta, self.openai_client, self.openai_model,
                    self.genres_ref, enrichment, cot=use_cot,
                )
                llm_called = True
                result = dict(llm_result)
                if h["slug"] and h["slug"] == llm_result["slug"]:
                    result["confidence"] = max(llm_result["confidence"], h["confidence"] + 0.05)

        # C5: top-2 y delta para revisión manual posterior
        top3 = h.get("top3", []) if 'h' in locals() else []
        slug_2 = top3[1][0] if len(top3) >= 2 else ""
        score_2 = top3[1][1] if len(top3) >= 2 else 0.0
        score_1 = top3[0][1] if len(top3) >= 1 else 0.0
        delta_1_2 = score_1 - score_2
        ctx["genre_slug_2"] = slug_2
        ctx["confidence_2"] = round(score_2, 3)
        ctx["ambiguous"] = bool(slug_2 and delta_1_2 < 0.15 and result.get("confidence", 0) < self.LOW_CONF_THRESHOLD)

        ctx["genre_slug"] = result["slug"]
        ctx["confidence"] = result["confidence"]
        ctx["rationale"] = result["rationale"]

        log_classification({
            "artist": req.artist,
            "title": req.title,
            "channel": meta.get("channel"),
            "release_year": meta.get("release_year"),
            "duration_sec": meta.get("duration_sec"),
            "mode": self.mode,
            "mb_tags": enrichment["mb_tags"],
            "discogs_styles": enrichment["discogs_styles"],
            "enrichment_status": ctx.get("enrichment_status", "skipped"),
            "heuristic_top3": h.get("top3", []),
            "heuristic_confidence": h.get("confidence", 0.0),
            "heuristic_signals": h.get("signals", {}),
            "llm_called": llm_called,
            "llm_slug": (llm_result or {}).get("slug"),
            "llm_confidence": (llm_result or {}).get("confidence"),
            "final_slug": result["slug"],
            "final_confidence": result["confidence"],
            "final_rationale": result["rationale"],
            "artist_prior": enrichment.get("artist_prior"),
            "slug_2": ctx.get("genre_slug_2"),
            "confidence_2": ctx.get("confidence_2"),
            "ambiguous": ctx.get("ambiguous", False),
        })

        logger.debug("classifier[%s]: %s (%.2f) ambig=%s",
                     self.mode, result["slug"], result["confidence"],
                     ctx.get("ambiguous"))
