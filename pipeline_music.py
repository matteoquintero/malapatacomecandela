# pipeline_music.py
# -*- coding: utf-8 -*-
"""
Pipeline CSV -> (YouTube ID via override o búsqueda) -> Clasificación 16 géneros -> Descarga
- Dedupe por manifest (artist|title) y por librería (archivos existentes)
- Soporta query_override con VIDEO_ID o URL (usa ID directo)
- Clasificador heurístico + fallback OpenAI opcional
- Ejecuta tu script bash dl-music-system.sh con el comando adecuado por género
- YouTube:
    * Early pick por canal oficial/Topic/Tema + match de título
    * Filtros anti-live/lyrics/making-of/compilados
    * Validación de canales no-oficiales (mínimo de subs + hints salsa)
    * Caché mensual de info de canales + caché de búsquedas (artist|title)
    * Contadores de cuota por canción y totales (con costos de la API)
- Modo SIN API:
    * Búsqueda con yt-dlp (ytsearch/ytmusicsearch/scsearch) para obtener IDs sin gastar cuota
    * Control por .env: SEARCH_MODE = no_api_first | api_first | no_api_only | api_only
    * NOAPI_SOURCES = ytsearch,ytmusicsearch,scsearch
"""

import os
import re
import csv
import shlex
import json
import math
import time
import argparse
import subprocess
import traceback
import unicodedata
import shutil
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional

# ========= .env =========
try:
    from dotenv import load_dotenv
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
    print("🧩 .env cargado (si existía).")
except Exception:
    print("⚠️ No se pudo cargar python-dotenv (opcional).")

# ========= CONFIG =========
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

DL_SCRIPT = os.getenv("DL_MUSIC_SCRIPT", os.path.join(
    os.path.dirname(__file__), "dl-music-system.sh"))
LIB_BASE_DIR = os.getenv("LIB_BASE_DIR", os.path.expanduser(
    "~/Music/mala_pata_come_candela"))
MANIFEST_FILE = os.getenv(
    "MANIFEST_FILE", os.path.join(PROJECT_DIR, "cache/manifest.csv"))

# Cachés
CHANNEL_CACHE_FILE = os.getenv("CHANNEL_CACHE_FILE", os.path.join(
    PROJECT_DIR, "cache/yt_channel_cache.json"))
CHANNEL_CACHE_TTL_DAYS = int(os.getenv("CHANNEL_CACHE_TTL_DAYS", "30"))
SEARCH_CACHE_FILE = os.getenv("SEARCH_CACHE_FILE", os.path.join(
    PROJECT_DIR, "cache/yt_search_cache.json"))
SEARCH_CACHE_TTL_DAYS = int(os.getenv("SEARCH_CACHE_TTL_DAYS", "45"))
MIN_SUBS_FOR_GENERIC_CHANNEL = int(
    os.getenv("MIN_SUBS_FOR_GENERIC_CHANNEL", "30000"))

# ===== Compatibilidad: reutilizar ubicaciones antiguas si existen =====
try:
    _OLD_MANIFEST = os.path.expanduser("~/.mala_pata/manifest.csv")
    if "MANIFEST_FILE" not in os.environ and os.path.exists(_OLD_MANIFEST):
        MANIFEST_FILE = _OLD_MANIFEST
        print(f"ℹ️ Compat: usando manifest heredado {_OLD_MANIFEST}")
    _OLD_CH_CACHE = os.path.expanduser("~/.mala_pata/yt_channel_cache.json")
    if "CHANNEL_CACHE_FILE" not in os.environ and os.path.exists(_OLD_CH_CACHE):
        CHANNEL_CACHE_FILE = _OLD_CH_CACHE
        print(f"ℹ️ Compat: usando cache canales heredado {_OLD_CH_CACHE}")
    _OLD_SRCH_CACHE = os.path.expanduser("~/.mala_pata/yt_search_cache.json")
    if "SEARCH_CACHE_FILE" not in os.environ and os.path.exists(_OLD_SRCH_CACHE):
        SEARCH_CACHE_FILE = _OLD_SRCH_CACHE
        print(f"ℹ️ Compat: usando cache búsquedas heredado {_OLD_SRCH_CACHE}")
except Exception:
    pass

# Heurística / límites
LOW_CONF_THRESHOLD = 0.80
YOUTUBE_MAX_RESULTS = int(os.getenv("YOUTUBE_MAX_RESULTS", "5"))
# LLM_ONLY | LLM_FALLBACK | HEURISTIC_ONLY
CLASSIFIER_MODE = os.getenv("CLASSIFIER_MODE", "LLM_FALLBACK")
PASS_HEURISTIC_TO_LLM = os.getenv(
    "PASS_HEURISTIC_TO_LLM", "false").lower() == "true"

# Presupuesto/contadores de YouTube API
YOUTUBE_CALL_BUDGET = int(os.getenv("YOUTUBE_CALL_BUDGET", "4000000"))
QUOTA_COSTS = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
}
_total_quota_units = 0
_total_api_calls: Dict[str, int] = defaultdict(int)

# ====== BÚSQUEDA SIN API (yt-dlp) ======
SEARCH_MODE = os.getenv("SEARCH_MODE", "no_api_first").strip().lower()
# opciones: no_api_first | api_first | no_api_only | api_only
NOAPI_SOURCES = [s.strip() for s in os.getenv(
    "NOAPI_SOURCES", "ytsearch,ytmusicsearch,scsearch").split(",") if s.strip()]
YTDLP_BIN = os.getenv("YTDLP_BIN", "yt-dlp")

print("⚙️ Config:")
print(f"   DL_SCRIPT      = {DL_SCRIPT}")
print(f"   LIB_BASE_DIR   = {LIB_BASE_DIR}")
print(f"   MANIFEST_FILE  = {MANIFEST_FILE}")
print(f"   OPENAI_MODEL   = {OPENAI_MODEL}")
print(
    f"   CHANNEL_CACHE  = {CHANNEL_CACHE_FILE} (TTL {CHANNEL_CACHE_TTL_DAYS}d)")
print(
    f"   SEARCH_CACHE   = {SEARCH_CACHE_FILE} (TTL {SEARCH_CACHE_TTL_DAYS}d)")
print(f"   YT BUDGET      = {YOUTUBE_CALL_BUDGET} unidades")
print(f"   SEARCH_MODE    = {SEARCH_MODE}")
print(f"   NOAPI_SOURCES  = {NOAPI_SOURCES}")
print(f"   YTDLP_BIN      = {YTDLP_BIN}")

# ========= OpenAI (opcional) =========
_openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        print("🤖 OpenAI: OK (API key detectada)")
    except Exception as e:
        print(f"⚠️ OpenAI no disponible: {e}")

# ========= YouTube API =========
_youtube = None
if YOUTUBE_API_KEY:
    try:
        from googleapiclient.discovery import build
        _youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        print("📺 YouTube API: OK (API key detectada)")
    except Exception as e:
        print(f"⚠️ YouTube API no disponible: {e}")
else:
    print("📺 YouTube API: SIN API key")

# ========= Helpers: cuota/budget =========


def _budget_left() -> int:
    return max(0, YOUTUBE_CALL_BUDGET - _total_quota_units)


def _can_spend(units: int) -> bool:
    return _budget_left() >= units


def _charge(kind: str, per_track: Dict):
    global _total_quota_units
    units = QUOTA_COSTS.get(kind, 1)
    _total_api_calls[kind] += 1
    _total_quota_units += units
    per_track["quota_units"] += units
    per_track["api_calls"][kind] = per_track["api_calls"].get(kind, 0) + 1


def _print_totals():
    print("\n🧮 Resumen global YouTube:")
    print(f"   Unidades gastadas:   {_total_quota_units}")
    print(f"   Presupuesto restante:{_budget_left()}")
    print("   Llamadas por endpoint:")
    for k in sorted(_total_api_calls):
        print(f"     • {k}: {_total_api_calls[k]}")


def _new_track_meter() -> Dict:
    return {"quota_units": 0, "api_calls": {}}

# ========= Utils texto =========


def _normalize_text(*parts: str) -> str:
    t = " ".join([p for p in parts if p]).lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def _simp_text(s: str) -> str:
    s = _strip_accents(s or "").lower().strip()
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def norm_key(artist: str, title: str) -> str:
    return f"{_simp_text(artist)}|{_simp_text(title)}"


# ========= Generos / comandos =========
GENRE_COMMAND: Dict[str, str] = {
    "son_cubano": "dl-son-cubano",
    "guajira_moderna": "dl-guajira-moderna",
    "guaracha": "dl-guaracha",
    "rumba_guaguanco": "dl-rumba-guaguanco",
    "afro_cuban_jazz_descarga": "dl-afro-cuban-jazz",
    "mambo": "dl-mambo",
    "cha_cha_cha": "dl-cha-cha-cha",
    "boogaloo": "dl-boogaloo",
    "salsa_dura_clasica": "dl-salsa-dura-clasica",
    "guaguanco_fusionado": "dl-guaguanco-fusionado",
    "exotica": "dl-exotica",
    "latin_soul": "dl-latin-soul",
    "plena_bomba": "dl-plena-bomba",
    "salsa_romantica": "dl-salsa-romantica",
    "timba": "dl-timba",
    "salsa_dura_revival": "dl-salsa-dura-revival",
}
ALL_SLUGS: List[str] = list(GENRE_COMMAND.keys())


def _norm_slug_name(s: str) -> str:
    s = (_strip_accents(s or "")).lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


# ========= Base rica (resumen) =========
GENRE_DB: List[Dict] = [
    {"name": "Son Cubano", "aliases": ["Son", "Son Montuno (genérico)"], "artists_key": ["Trío Matamoros", "Arsenio Rodríguez", "Septeto Nacional", "Ignacio Piñeiro", "Compay Segundo", "Eliades Ochoa"], "rhythm_traits": ["tumbao de bajo caminante", "montuno", "llamada y respuesta"], "instrumentation": {
        "core": ["tres cubano", "guitarra", "piano", "bongó", "maracas", "claves", "contrabajo", "trompeta"], "optional": ["conga", "flauta", "violín"]}, "signature_tracks": ["Lágrimas Negras", "Échale Salsita", "Bruca Maniguá"], "negative": ["salsa romantica", "bachata", "reggaeton"]},
    {"name": "Guajira Moderna", "aliases": ["Guajira Son", "Son Montuno Lento"], "artists_key": ["Guillermo Portabales", "Compay Segundo", "Eliades Ochoa"], "rhythm_traits": ["tumbao suave", "énfasis melódico y poético"], "instrumentation": {
        "core": ["tres", "guitarra", "bongó", "maracas", "contrabajo", "claves"], "optional": ["flauta", "violín"]}, "signature_tracks": ["El Carretero", "Chan Chan", "Rico Vacilón"], "negative": ["mambo explosivo", "guaracha rapida", "salsa romantica"]},
    {"name": "Guaracha", "aliases": [], "artists_key": ["Beny Moré", "Celia Cruz", "Ñico Saquito", "Sonora Matancera"], "rhythm_traits": ["coros rápidos", "soneo juguetón", "doble sentido"], "instrumentation": {"core": ["tres", "guitarra",
                                                                                                                                                                                                                            "piano", "bongó", "maracas", "claves", "contrabajo", "trompeta"], "optional": ["conga", "saxofón"]}, "signature_tracks": ["Cuidadito Compay Gallo", "María Cristina", "Francisco Guayabal"], "negative": ["balada", "romantica"]},
    {"name": "Rumba Guaguancó", "aliases": ["Guaguancó"], "artists_key": ["Los Muñequitos de Matanzas", "Yoruba Andabo", "Clave y Guaguancó", "Los Papines"], "rhythm_traits": ["polirritmia", "quinto improvisador", "vacunao"], "instrumentation": {
        "core": ["quinto", "tres golpes", "tumba", "claves", "guagua", "voz", "coro"], "optional": ["chekeré", "palmas"]}, "signature_tracks": ["Rumba pa' los rumberos"], "negative": ["mambo big band", "metales salsa pesados"]},
    {"name": "Afro Cuban Jazz Descarga", "aliases": ["Afro-Cuban Jazz", "Latin Jazz (clásico)", "Descarga"], "artists_key": ["Machito", "Mario Bauzá", "Tito Puente", "Cachao", "Mongo Santamaría", "Cal Tjader", "Dizzy Gillespie"], "rhythm_traits": ["tema–solos–tema", "descarga"], "instrumentation": {
        "core": ["piano", "bajo", "contrabajo", "congas", "timbales", "bongó", "metales", "saxos"], "optional": ["batá", "flauta", "vibráfono"]}, "signature_tracks": ["Tanga", "Manteca", "Afro Blue", "Descarga Cachao"], "negative": ["balada", "romantica"]},
    {"name": "Mambo", "aliases": [], "artists_key": ["Pérez Prado", "Tito Puente", "Machito"], "rhythm_traits": ["síncopas cortantes", "breaks de metales", "mambos instrumentales"], "instrumentation": {
        "core": ["piano", "bajo", "congas", "timbales", "bongó", "trompetas", "trombones", "saxofones"]}, "signature_tracks": ["Mambo No. 5", "Ran Kan Kan", "Mambo Inn"], "negative": ["charanga pura"]},
    {"name": "Cha Cha Cha", "aliases": ["Chachachá", "Cha-cha-cha"], "artists_key": ["Orquesta América", "Orquesta Aragón", "José Fajardo", "Enrique Jorrín"], "rhythm_traits": ["1–2–cha-cha-chá", "charanga"], "instrumentation": {
        "core": ["flauta", "violines", "fondo piano/contrabajo", "timbales", "güiro", "maracas"]}, "signature_tracks": ["La Engañadora", "Me lo Dijo Adela", "El Bodeguero"], "negative": ["trombones pesados 70s"]},
    {"name": "Boogaloo", "aliases": ["Latin Boogaloo", "Bugalú"], "artists_key": ["Pete Rodríguez", "Joe Cuba", "Johnny Colón", "Ray Barretto"], "rhythm_traits": ["groove soul", "spanglish", "shing-a-ling", "watusi"], "instrumentation": {
        "core": ["órgano", "piano", "bajo eléctrico", "congas", "timbales", "bongó", "metales"]}, "signature_tracks": ["I Like It Like That", "Bang Bang", "Boogaloo Blues"], "negative": ["latin soul balada suave"]},
    {"name": "Salsa Dura Clásica", "aliases": ["Salsa Brava", "Salsa 70s"], "artists_key": ["Willie Colón", "Héctor Lavoe", "Rubén Blades", "Ray Barretto", "Eddie Palmieri", "Fania All Stars", "Sonora Ponceña", "Raphy Leavitt"], "rhythm_traits": [
        "coro–soneo intenso", "mambos de metales", "descargas", "montuno"], "instrumentation": {"core": ["piano", "bajo", "congas", "bongó", "timbales", "trombones", "trompetas", "coros"]}, "signature_tracks": ["Aguanile", "Plástico", "Indestructible", "Quítate Tú"], "negative": ["romantica", "erotica"]},
    {"name": "Guaguancó Fusionado", "aliases": [], "artists_key": ["Eddie Palmieri", "Irakere", "Batacumbele", "Los Van Van"], "rhythm_traits": ["toque rumbero en salsa", "bloques rumberos"],
        "instrumentation": {"core": ["congas/quinto", "piano", "bajo", "metales", "coros"], "optional": ["batá"]}, "signature_tracks": ["Plástico (intro rumbera)"], "negative": ["puro folklor sin orquesta"]},
    {"name": "Exotica", "aliases": [], "artists_key": ["Martin Denny", "Les Baxter", "Yma Sumac", "Arthur Lyman"], "rhythm_traits": ["atmósfera cinematográfica", "selva", "vibráfono"],
        "instrumentation": {"core": ["percusión suave", "marimba/vibráfono", "cuerdas", "flautas"]}, "signature_tracks": ["Quiet Village", "Taboo"], "negative": ["salsa dura", "boogaloo"]},
    {"name": "Latin Soul", "aliases": [], "artists_key": ["Joe Bataan", "Ralfi Pagán", "Harvey Averne", "Malo"], "rhythm_traits": ["balada soul con conga", "órgano", "doo-wop"], "instrumentation": {"core": ["voz soul",
                                                                                                                                                                                                               "órgano/guitarra", "bajo", "batería", "conga/bongó"], "optional": ["metales suaves"]}, "signature_tracks": ["Ordinary Guy", "Gypsy Woman", "I'm Your Puppet"], "negative": ["boogaloo shing a ling explosivo"]},
    {"name": "Plena Bomba", "aliases": ["Plena", "Bomba"], "artists_key": ["Rafael Cortijo", "Ismael Rivera", "Pleneros de la 21", "Viento de Agua"], "rhythm_traits": ["llamada-respuesta", "panderetas", "barriles"],
        "instrumentation": {"core": ["panderetas y güiro", "barriles", "maraca", "cuá"]}, "signature_tracks": ["Maquinolandera", "El Bombón de Elena"], "negative": ["metales pesados salsa (si no es fusión)"]},
    {"name": "Salsa Romántica", "aliases": ["Salsa sensual", "Salsa erótica"], "artists_key": ["Lalo Rodríguez", "Frankie Ruiz", "Eddie Santiago", "Gilberto Santa Rosa", "Jerry Rivera", "Luis Enrique"], "rhythm_traits": ["coro emotivo", "menos agresividad percusiva", "producción pulida"], "instrumentation": {
        "core": ["piano", "bajo", "congas/bongó/timbales suaves", "metales contenidos", "voz protagonista"], "optional": ["sintetizadores"]}, "signature_tracks": ["Ven Devórame Otra Vez", "Desnúdate Mujer", "Amores Como el Nuestro"], "negative": ["trombones agresivos 70s", "soneo largo"]},
    {"name": "Timba", "aliases": [], "artists_key": ["NG La Banda", "Los Van Van", "Charanga Habanera", "Pupy y Los Que Son Son", "Manolín"], "rhythm_traits": ["bloqueos y cortes", "bajo protagónico", "cambios súbitos"], "instrumentation": {
        "core": ["piano", "bajo eléctrico", "batería", "congas", "timbales", "metales", "coros"], "optional": ["teclados"]}, "signature_tracks": ["Te Pone la Cabeza Mala", "La Habana Me Llama"], "negative": ["boogaloo", "salsa romantica"]},
    {"name": "Salsa Dura Revival", "aliases": ["Neosalsa", "Salsa dura moderna"], "artists_key": ["La-33", "Spanish Harlem Orchestra", "La Excelencia", "El Macabeo", "La Mambanegra", "Tromboranga", "Los Hacheros"], "rhythm_traits": [
        "mambos pesados", "soneo vivo", "producción nítida"], "instrumentation": {"core": ["piano", "bajo", "congas/bongó/timbales", "trombones/trompetas", "coros fuertes"]}, "signature_tracks": ["La Pantera Mambo", "Salsa Dura"], "negative": ["romantica noventera"]},
]


def _derive_heuristics():
    keywords = defaultdict(list)
    artists_hint = defaultdict(list)
    negative = defaultdict(list)
    for g in GENRE_DB:
        slug = _norm_slug_name(g["name"])
        kws = []
        kws += [_simp_text(a) for a in g.get("aliases", [])]
        kws += [_simp_text(x) for x in g.get("rhythm_traits", [])]
        inst = g.get("instrumentation", {})
        for lst in inst.values():
            kws += [_simp_text(x) for x in lst]
        kws += [_simp_text(x) for x in g.get("signature_tracks", [])]
        dedup = []
        seen = set()
        for w in kws:
            w = w.strip()
            if not w or len(w) < 3:
                continue
            if w in seen:
                continue
            seen.add(w)
            dedup.append(w)
        keywords[slug] = dedup
        artists_hint[slug] = [_simp_text(a) for a in g.get("artists_key", [])]
        negative[slug] = [_simp_text(x) for x in g.get("negative", [])]
    return dict(keywords), dict(artists_hint), dict(negative)


KEYWORDS, ARTISTS_HINT, NEGATIVE_RULES = _derive_heuristics()

# ========= Heurística + LLM =========


class HeuristicResult:
    def __init__(self, slug: str, score: float, reasons: List[str]):
        self.slug = slug
        self.score = score
        self.reasons = reasons


def heuristic_scores(meta: Dict) -> List[HeuristicResult]:
    text = _normalize_text(meta.get("title", ""), meta.get(
        "description", ""), meta.get("channel", ""))
    artist_text = _simp_text(meta.get("artist", ""))
    scores: Dict[str, float] = defaultdict(float)
    reasons: Dict[str, List[str]] = defaultdict(list)

    for slug, words in KEYWORDS.items():
        for w in words:
            if w and w in text:
                scores[slug] += 1.8
                reasons[slug].append(f"kw:{w}")

    for slug, arts in ARTISTS_HINT.items():
        for a in arts:
            if a in artist_text or a in text:
                scores[slug] += 2.2
                reasons[slug].append(f"artist:{a}")

    for slug, negs in NEGATIVE_RULES.items():
        for n in negs:
            if n in text:
                scores[slug] -= 1.2
                reasons[slug].append(f"neg:{n}")

    if all(v == 0.0 for v in scores.values()):
        scores["salsa_dura_clasica"] = 0.1
        reasons["salsa_dura_clasica"].append("default:bias")

    out = [HeuristicResult(slug=s, score=scores.get(
        s, 0.0), reasons=reasons.get(s, [])) for s in ALL_SLUGS]
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def softmax(scores: List[float]) -> List[float]:
    if not scores:
        return []
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    tot = sum(exps) or 1.0
    return [e/tot for e in exps]


# ========= Referencia de géneros para el LLM =========
# Opción A: apunta a un archivo con el JSON completo usando GENRE_REF_PATH
# Opción B: deja vacío y se deriva un JSON compacto desde GENRE_DB
GENRE_REF_PATH = os.getenv("GENRE_REF_PATH", "")
_genres_reference_text = ""


def _load_genres_reference():
    global _genres_reference_text
    if GENRE_REF_PATH and os.path.exists(GENRE_REF_PATH):
        try:
            with open(GENRE_REF_PATH, "r", encoding="utf-8") as f:
                _genres_reference_text = f.read()
                print(
                    f"📚 Referencia de géneros cargada desde {GENRE_REF_PATH} ({len(_genres_reference_text)} chars).")
                return
        except Exception as e:
            print(f"⚠️ No se pudo leer GENRE_REF_PATH: {e}")

    # Fallback: derivar una referencia compacta desde GENRE_DB
    try:
        ref = []
        for g in GENRE_DB:
            ref.append({
                "name": g["name"],
                "aliases": g.get("aliases", []),
                "rhythm_traits": g.get("rhythm_traits", []),
                "instrumentation_core": g.get("instrumentation", {}).get("core", []),
                "artists_key": g.get("artists_key", []),
                "signature_tracks": g.get("signature_tracks", [])
            })
        _genres_reference_text = json.dumps(
            {"genres": ref}, ensure_ascii=False, indent=2)
        print(
            f"📚 Referencia de géneros derivada de GENRE_DB ({len(_genres_reference_text)} chars).")
    except Exception as e:
        print(f"⚠️ No se pudo construir referencia de géneros: {e}")
        _genres_reference_text = ""


_load_genres_reference()


def build_prompt(meta: Dict) -> str:
    slugs_csv = ", ".join(ALL_SLUGS)

    user_case = (
        f"Título: {meta.get('title', '')}\n"
        f"Artista: {meta.get('artist', '')}\n"
        f"Canal: {meta.get('channel', '')}\n"
        f"Descripción: {meta.get('description', '')}\n"
    )

    rules = f"""
        Eres musicólogo experto en salsa y géneros afrolatinos. Clasifica EXACTAMENTE en uno de estos 16 slugs: {slugs_csv}.
        No inventes géneros. No uses valores por defecto. Si hay poca info, razona por evidencias y descarta explícitamente lo que NO encaja.

        Evalúa y justifica con 4 ejes:
        1) Ritmo e instrumentación (groove/clave; bajo/percusión; metales vs charanga; órgano/guitarra; batería)
        2) Estilo vocal y lírica (spanglish/doo‑wop vs soneo/montuno; balada)
        3) Estructura (verso→coro→montuno; mambos; descargas; bloques; duración)
        4) Contexto histórico/estético (NY 60s boogaloo; Fania 70s; Cuba 90s timba; charanga 50s, etc.)

        Formato de salida (JSON estricto):
        {{
        "slug": "<uno de {slugs_csv}>",
        "confidence": 0.0-1.0,
        "rationale": "2-4 frases con evidencias (referidas al caso)",
        "checks": {{
            "rhythm_instrumentation": {{"valid": true/false, "notes": "…"}},
            "vocal_lyrics":         {{"valid": true/false, "notes": "…"}},
            "structure":            {{"valid": true/false, "notes": "…"}},
            "historical_context":   {{"valid": true/false, "notes": "…"}}
        }},
        "disqualified_genres": [
            {{"slug":"…","reason":"…"}}
        ]
        }}

        Ejemplos guía rápidos:
        - "Pow Wow" – Manny Corchado → "boogaloo"
        - "Ordinary Guy" – Joe Bataan → "latin_soul"
        - "El Preso" – Fruko → "salsa_dura_clasica"
        - "La Pantera Mambo" – La‑33 → "salsa_dura_revival"
        - "No Te Critico" – Tony Pabón → "boogaloo" (groove R&B, spanglish/latinsoul vibe, estructura verso‑coro repetitiva, sin montuno largo ni mambos pesados)

        Caso a clasificar:
        {user_case}

        JSON de referencia (resumen de géneros):
        {_genres_reference_text}
    """.strip()

    return rules


def llm_call(meta: Dict) -> Dict:
    if not _openai_client:
        return {"slug": "salsa_dura_clasica", "confidence": 0.72, "rationale": "fallback sin OpenAI", "checks": {}, "disqualified_genres": []}

    prompt = build_prompt(meta)
    try:
        kwargs = dict(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Eres un musicólogo riguroso. Responde SOLO JSON válido según el esquema; no inventes campos ni géneros."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        try:
            kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass

        comp = _openai_client.chat.completions.create(**kwargs)
        text = comp.choices[0].message.content.strip()

        if not text.startswith("{"):
            m = re.search(r"\{.*\}", text, flags=re.S)
            text = m.group(0) if m else "{}"

        data = json.loads(text)

        slug_raw = (data.get("slug") or "").strip()
        slug_norm = slug_raw.lower().replace("-", "_").replace(" ", "_")
        slug = slug_norm if slug_norm in GENRE_COMMAND else "salsa_dura_clasica"

        conf = float(data.get("confidence", 0.7))
        conf = max(0.0, min(1.0, conf))

        return {
            "slug": slug,
            "confidence": conf,
            "rationale": (data.get("rationale") or "").strip(),
            "checks": data.get("checks", {}) or {},
            "disqualified_genres": data.get("disqualified_genres", []) or [],
        }

    except Exception:
        return {"slug": "salsa_dura_clasica", "confidence": 0.7, "rationale": "fallback por error de LLM", "checks": {}, "disqualified_genres": []}


def classify(meta: Dict) -> Dict:
    use_heur_gate = (CLASSIFIER_MODE != "LLM_ONLY")

    print("   🤖 Clasificando (heurística)...")
    hres = heuristic_scores(meta)
    top = hres[:5]
    raw_scores = [x.score for x in top]
    probs = softmax(raw_scores) if any(
        s for s in raw_scores) else [0.0]*len(top)
    best = top[0] if top else HeuristicResult(
        "salsa_dura_clasica", 0.0, ["default"])
    conf_heur = probs[0] if probs else 0.0
    print(
        f"   🔎 Heurística top: {[(t.slug, round(s, 2)) for t, s in zip(top, raw_scores)]}")

    # Si estás en LLM_ONLY, NO uses puerta por heurística
    if use_heur_gate and conf_heur >= LOW_CONF_THRESHOLD:
        rationale = f"Heurística: {', '.join(best.reasons[:4])}"
        print(
            f"   ✅ Heurística suficiente → {best.slug} ({round(conf_heur, 3)})")
        return {
            "slug": best.slug,
            "confidence": round(float(conf_heur), 3),
            "rationale": rationale,
            "command": GENRE_COMMAND[best.slug],
        }

    print("   🧠 LLM …")
    prompt_meta = dict(meta)
    # Solo pasar heuristic_top si lo pides explícitamente
    if PASS_HEURISTIC_TO_LLM:
        prompt_meta["heuristic_top"] = [
            (t.slug, t.score, t.reasons[:2]) for t in top]
    else:
        prompt_meta["heuristic_top"] = []

    llm = llm_call(prompt_meta)
    slug = llm.get("slug", best.slug)
    conf_llm = float(llm.get("confidence", 0.72))
    rationale = f"{llm.get('rationale', 'sin detalle')}"

    # En LLM_ONLY no mezcles con heurística; en fallback, sí puedes suavemente
    if CLASSIFIER_MODE == "LLM_ONLY":
        final_conf = conf_llm
    else:
        final_conf = max(conf_llm, conf_heur + 0.05)

    print(f"   ✅ LLM propone → {slug} ({round(final_conf, 3)})")
    return {
        "slug": slug,
        "confidence": round(final_conf, 3),
        "rationale": rationale,
        "command": GENRE_COMMAND[slug],
    }

# ========= Dedupe =========


def build_library_index(base_dir: str) -> set:
    print(f"📚 Indexando librería en: {base_dir}")
    known = set()
    if not os.path.exists(base_dir):
        print("   ℹ️ Directorio no existe, se saltará el dedupe por archivos.")
        return known
    cnt = 0
    for _, _, files in os.walk(base_dir):
        for fn in files:
            if fn.lower().endswith(".mp3"):
                name = os.path.splitext(fn)[0]
                if " - " in name:
                    a, t = name.split(" - ", 1)
                    known.add(norm_key(a, t))
                    cnt += 1
    print(f"   ✅ {cnt} MP3 indexados para dedupe por nombre.")
    return known


def ensure_manifest(file_path: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if not os.path.exists(file_path):
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts", "artist", "title", "norm_key", "video_id",
                       "genre_slug", "command", "status", "filepath"])


def load_manifest_keys(file_path: str) -> set:
    keys = set()
    if os.path.exists(file_path):
        with open(file_path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                nk = (row.get("norm_key") or "").strip()
                if nk:
                    keys.add(nk)
    return keys


def append_manifest_row(file_path: str, artist: str, title: str, video_id: str, genre_slug: str, command: str, status: str, filepath: str):
    ensure_manifest(file_path)
    with open(file_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            datetime.now().isoformat(timespec="seconds"),
            artist, title, norm_key(artist, title),
            video_id, genre_slug, command, status, filepath
        ])


# ========= Reglas YouTube (filtros) =========
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

LIVE_BAD_PAT = re.compile(
    r"\b(live|en vivo|en directo|directo|concert|session|sessions|karaoke|cover|envivo)\b", re.I)
STUDIO_GOOD_PAT = re.compile(
    r"\b(remaster(?:ed)?|album version|studio|estudio|official audio|audio oficial)\b", re.I)
FULL_ALBUM_BAD_PAT = re.compile(
    r"\b(full album|álbum completo|album completo|long mix|dj mix|megamix)\b", re.I)
LYRICS_BAD_PAT = re.compile(
    r"\b(lyrics?|letra|subtitulado|subtitulada|subtitles?)\b", re.I)
MIX_BAD_PAT = re.compile(r"\b(remix|mix|megamix)\b", re.I)
CONTEXT_BAD_PAT = re.compile(
    r"\b(parque|plaza|catedral|monumento|iglesia|barrio|calle|feria|festival|evento|homenaje|tributo|ensayo|soundcheck|"
    r"serenata|boda|quincea(?:n|ñ)era|navidad|a(?:n|ñ)o nuevo|carnaval|fiesta patronal|tarima|kermesse)\b", re.I)
SERIES_BAD_PAT = re.compile(
    r"\b(vol(?:\.|\s)?\d+|volume\s?\d+|parte\s?\d+|part\s?\d+|episodio|episode|cap[íi]tulo)\b", re.I)
COMPILATION_BAD_PAT = re.compile(
    r"\b(non[- ]?stop|nonstop|compilado|antolog[ií]a|lo mejor de|greatest hits|colecci[oó]n)\b", re.I)
MAKING_BAD_PAT = re.compile(
    r"\b(making of|behind the scenes|detr[aá]s de c[aá]maras|documental|entrevista|studio vlog)\b", re.I)

SALSA_CHANNEL_HINTS = [
    "salsa", "latin", "afro", "guaguanco", "son", "timba", "boogaloo", "charanga", "rumba", "matancera", "ponceña", "fania"
]

STOPWORDS_TITLE = {
    "el", "la", "los", "las", "de", "del", "y", "o", "u", "en", "con", "por", "para",
    "a", "al", "un", "una", "uno", "unos", "unas", "the", "of", "and", "feat", "ft"
}


def _key_tokens(title: str) -> set:
    toks = []
    for t in _simp_text(title).split():
        if len(t) >= 4 and t not in STOPWORDS_TITLE:
            toks.append(t)
    return set(toks)


def _title_similarity(query_title: str, candidate_title: str) -> float:
    q = set(t for t in _simp_text(query_title).split()
            if t and t not in STOPWORDS_TITLE)
    c = set(t for t in _simp_text(candidate_title).split() if t)
    if not q:
        return 0.0
    inter = len(q & c)
    return inter / max(1, len(q))


def iso8601_duration_to_seconds(d: str) -> int:
    if not d:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mnt = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h*3600 + mnt*60 + s

# ========= Artista principal =========


def primary_artist_name(artist: str) -> str:
    s = artist or ""
    s = re.sub(r"\s+(y|&|con|feat\.?|ft\.?)\s+.+$", "", s, flags=re.I)
    return s.strip()

# ======= Cachés =======


def _load_json_cache(path: str) -> Dict:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_json_cache(path: str, data: Dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _channel_from_cache(cache: Dict, channel_id: str) -> Optional[Dict]:
    rec = cache.get(channel_id)
    if not rec:
        return None
    try:
        ts = datetime.fromisoformat(rec.get("ts"))
    except Exception:
        return None
    if datetime.now() - ts > timedelta(days=CHANNEL_CACHE_TTL_DAYS):
        return None
    return rec


def _update_channel_cache_batch(channel_meta: Dict[str, Dict]):
    cache = _load_json_cache(CHANNEL_CACHE_FILE)
    now = datetime.now().isoformat(timespec="seconds")
    for cid, meta in channel_meta.items():
        cache[cid] = {
            "ts": now,
            "title": meta.get("title") or "",
            "description": meta.get("description") or "",
            "subs": int(meta.get("subs") or 0)
        }
    _save_json_cache(CHANNEL_CACHE_FILE, cache)


def _get_channels_info_batch(channel_ids: List[str], per_track: Dict) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    cache = _load_json_cache(CHANNEL_CACHE_FILE)
    missing = []
    for cid in channel_ids:
        rec = _channel_from_cache(cache, cid)
        if rec:
            out[cid] = {"title": rec.get("title", ""), "description": rec.get(
                "description", ""), "subs": int(rec.get("subs", 0))}
        else:
            missing.append(cid)

    if missing and _youtube and _can_spend(QUOTA_COSTS["channels.list"]):
        try:
            _charge("channels.list", per_track)
            resp = _youtube.channels().list(id=",".join(
                missing), part="statistics,snippet").execute()
            merged_meta = {}
            for it in resp.get("items", []):
                cid = it["id"]
                title = it["snippet"].get("title", "") or ""
                desc = it["snippet"].get("description", "") or ""
                subs = int(it.get("statistics", {}).get(
                    "subscriberCount", "0") or 0)
                merged_meta[cid] = {"title": title,
                                    "description": desc, "subs": subs}
                out[cid] = {"title": title, "description": desc, "subs": subs}
            if merged_meta:
                _update_channel_cache_batch(merged_meta)
        except Exception as e:
            print(f"   ℹ️ No se pudo leer info de canales: {e}")
    return out

# ========= Oficialidad / Topic =========


def _score_channel_officiality(artist: str, channel_title: str) -> float:
    a = _simp_text(artist)
    ch = _simp_text(channel_title)
    if not a or not ch:
        return 0.0
    score = 0.0
    if ch == a:
        score += 3.0
    if ch.startswith(a):
        score += 2.0
    if a in ch:
        score += 1.2
    if re.search(r"\b(oficial|official)\b", ch):
        score += 2.5
    if re.search(r"\b(topic|tema)\b", ch) and a in ch:
        score += 2.5
    if re.search(r"\b(salsa|radio|esquina|para todos|mix|hits|records|tv|canal|music channel)\b", ch):
        score -= 1.0
    return score


def _channel_seems_salsa(title: str, desc: str) -> bool:
    st = _simp_text(title + " " + (desc or ""))
    return any(h in st for h in SALSA_CHANNEL_HINTS)

# ========= Wrappers YouTube con cuota =========


def _yt_search_channels(q: str, per_track: Dict) -> List[Dict]:
    if not _youtube or not _can_spend(QUOTA_COSTS["search.list"]):
        return []
    try:
        _charge("search.list", per_track)
        resp = _youtube.search().list(
            q=q, part="snippet", maxResults=10, type="channel",
            order="relevance", relevanceLanguage="es", regionCode="CO"
        ).execute()
        return resp.get("items", [])
    except Exception as e:
        print(f"   ℹ️ search.channels error: {e}")
        return []


def _yt_search_videos(q: str, max_results: int, per_track: Dict, channelId: Optional[str] = None) -> List[Dict]:
    if not _youtube or not _can_spend(QUOTA_COSTS["search.list"]):
        return []
    try:
        _charge("search.list", per_track)
        kwargs = dict(q=q, part="snippet", maxResults=max_results, type="video",
                      order="relevance", videoEmbeddable="true",
                      relevanceLanguage="es", regionCode="CO")
        if channelId:
            kwargs["channelId"] = channelId
        resp = _youtube.search().list(**kwargs).execute()
        return resp.get("items", [])
    except Exception as e:
        print(f"   ℹ️ search.videos error: {e}")
        return []


def _yt_videos_list(ids: List[str], per_track: Dict, part: str = "contentDetails,statistics") -> Dict[str, Dict]:
    if not ids or not _youtube or not _can_spend(QUOTA_COSTS["videos.list"]):
        return {}
    try:
        _charge("videos.list", per_track)
        resp = _youtube.videos().list(id=",".join(ids), part=part).execute()
        return {it["id"]: it for it in resp.get("items", [])}
    except Exception as e:
        print(f"   ℹ️ videos.list error: {e}")
        return {}

# ========= Buscar canales "oficial-like" (con cuota) =========


def search_official_channels(artist: str, per_track: Dict, max_channels: int = 5) -> List[Dict]:
    if not _youtube:
        return []
    try:
        pa = primary_artist_name(artist) or artist
        chans_a = _yt_search_channels(pa, per_track)
        chans_b = _yt_search_channels(
            f"{pa} topic", per_track) + _yt_search_channels(f"{pa} tema", per_track)

        merged = {}
        for it in (chans_a + chans_b):
            ct = it["snippet"]["title"]
            cid = it["id"]["channelId"]
            sc = _score_channel_officiality(pa, ct)
            c = {"channel_id": cid, "channel_title": ct, "score": sc}
            if cid not in merged or sc > merged[cid]["score"]:
                merged[cid] = c
        chans = list(merged.values())
        chans.sort(key=lambda x: x["score"], reverse=True)
        out = [c for c in chans if c["score"] >= 2.0][:max_channels]

        if out:
            print("   🏷️ Canales 'oficiales' detectados:")
            for c in out:
                print(
                    f"     · {c['channel_title']} (score:{c['score']:.1f}) id:{c['channel_id']}")
        return out
    except Exception as e:
        print(f"   ℹ️ No se pudo buscar canales: {e}")
        return []

# ========= Búsqueda YouTube con caché (API) =========


def _search_cache_get(artist: str, title: str) -> Optional[List[Dict]]:
    cache = _load_json_cache(SEARCH_CACHE_FILE)
    key = f"{_simp_text(artist)}|{_simp_text(title)}"
    rec = cache.get(key)
    if not rec:
        return None
    try:
        ts = datetime.fromisoformat(rec.get("ts"))
        if datetime.now() - ts > timedelta(days=SEARCH_CACHE_TTL_DAYS):
            return None
        return rec.get("items") or None
    except Exception:
        return None


def _search_cache_put(artist: str, title: str, items: List[Dict]):
    cache = _load_json_cache(SEARCH_CACHE_FILE)
    key = f"{_simp_text(artist)}|{_simp_text(title)}"
    cache[key] = {"ts": datetime.now().isoformat(
        timespec="seconds"), "items": items[:YOUTUBE_MAX_RESULTS]}
    _save_json_cache(SEARCH_CACHE_FILE, cache)


def search_youtube_id(query: str, max_results: int, artist_hint: str, title_hint: str, per_track: Dict) -> List[Dict]:
    cached = _search_cache_get(artist_hint, title_hint)
    if cached:
        print("   ♻️ Usando resultados de caché de búsqueda (artist|title).")
        return cached

    pa = primary_artist_name(artist_hint) if artist_hint else ""
    items: List[Dict] = []

    # 1) Canal oficial/Topic
    if (artist_hint or pa) and title_hint:
        chans = search_official_channels(
            pa or artist_hint, per_track, max_channels=3)
        for ch in chans:
            vids = _yt_search_videos(
                title_hint, max_results, per_track, channelId=ch["channel_id"])
            got = []
            for idx, it in enumerate(vids, start=1):
                cand = {
                    "video_id": it["id"]["videoId"],
                    "title": it["snippet"]["title"],
                    "channel": it["snippet"]["channelTitle"],
                    "channel_id": it["snippet"]["channelId"],
                    "description": it["snippet"].get("description", "") or "",
                    "_official_channel": True,
                    "_rank": idx
                }
                sim = _title_similarity(title_hint, cand["title"])
                if sim >= 0.62:
                    got.append(cand)
            if got:
                print(
                    f"   🎯 Videos desde canal oficial {ch['channel_title']}: {len(got)} (título similar)")
                meta = _yt_videos_list([x["video_id"] for x in got], per_track)
                for x in got:
                    det = meta.get(x["video_id"], {})
                    x["duration_sec"] = iso8601_duration_to_seconds(
                        det.get("contentDetails", {}).get("duration", ""))
                    x["views"] = int(
                        det.get("statistics", {}).get("viewCount", "0") or 0)
                _search_cache_put(artist_hint, title_hint, got)
                return got  # early return

    # 2) Búsqueda general STRICT con filtros negativos
    negatives = [
        '-live', '-"en vivo"', '-"en directo"', '-directo', '-concert',
        '-session', '-sessions', '-karaoke', '-cover', '-"full album"',
        '-"álbum completo"', '-"album completo"', '-lyrics', '-letra',
        '-subtitles', '-subtitulado', '-subtitulada', '-mix', '-megamix'
    ]
    strict_items = []
    q_strict = f'{query} ' + " ".join(negatives)
    print(f"   🔎 YouTube search (strict): {q_strict}")
    vids = _yt_search_videos(q_strict, max_results, per_track)
    for idx, it in enumerate(vids, start=1):
        strict_items.append({
            "video_id": it["id"]["videoId"],
            "title": it["snippet"]["title"],
            "channel": it["snippet"]["channelTitle"],
            "channel_id": it["snippet"]["channelId"],
            "description": it["snippet"].get("description", "") or "",
            "_rank": idx
        })
    print(f"   🔍 YouTube resultados (strict): {len(strict_items)}")

    if strict_items:
        meta = _yt_videos_list([x["video_id"]
                               for x in strict_items], per_track)
        for x in strict_items:
            det = meta.get(x["video_id"], {})
            x["duration_sec"] = iso8601_duration_to_seconds(
                det.get("contentDetails", {}).get("duration", ""))
            x["views"] = int(
                det.get("statistics", {}).get("viewCount", "0") or 0)
        ch_ids = list({x["channel_id"] for x in strict_items})
        ch_meta = _get_channels_info_batch(ch_ids, per_track)
        for x in strict_items:
            cm = ch_meta.get(x["channel_id"], {})
            x["channel_title_full"] = cm.get("title") or x.get("channel", "")
            x["channel_desc"] = cm.get("description", "")
            x["channel_subs"] = int(cm.get("subs") or 0)

    _search_cache_put(artist_hint, title_hint, strict_items)
    return strict_items

# ========= BÚSQUEDA SIN API (yt-dlp) =========


def _yt_dlp_available() -> bool:
    path = shutil.which(YTDLP_BIN)
    if not path:
        print(
            f"   ℹ️ {YTDLP_BIN} no está en PATH. Instala con: pip install yt-dlp")
        return False
    return True


def yt_dlp_search(query: str, max_results: int = 5, source: str = "ytsearch") -> List[Dict]:
    """
    source: ytsearch | ytmusicsearch | scsearch
    Devuelve items con: video_id, title, channel, description (vacía), _rank, _noapi
    """
    if not _yt_dlp_available():
        return []
    try:
        # Usamos --print con plantilla para obtener id|title|uploader en líneas separadas
        template = "%(id)s|||%(title)s|||%(uploader)s"
        cmd = [
            YTDLP_BIN, f"{source}{max_results}:{query}",
            "--skip-download",
            "--print", template
        ]
        out = subprocess.run(cmd, capture_output=True,
                             text=True, check=True).stdout.strip().splitlines()
        items = []
        for line in out:
            parts = line.split("|||")
            if len(parts) >= 3:
                vid = parts[0].strip()
                title = parts[1].strip()
                uploader = parts[2].strip()
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    items.append({
                        "video_id": vid,
                        "title": title,
                        "channel": uploader,
                        "channel_id": "",            # no disponible sin API
                        "description": "",           # no disponible sin API
                        "channel_title_full": uploader,
                        "channel_desc": "",
                        "channel_subs": 0,           # desconocido
                        "_rank": len(items) + 1,
                        "_noapi": True
                    })
        print(f"   🔍 {source} resultados (no API): {len(items)}")
        return items[:max_results]
    except Exception as e:
        print(f"   ℹ️ yt-dlp search error ({source}): {e}")
        return []


def find_candidates_noapi(artist: str, title: str, max_results: int = 5) -> List[Dict]:
    """Intenta múltiples fuentes sin API en orden definido por NOAPI_SOURCES."""
    query = f"{artist} {title}"
    all_items: List[Dict] = []
    tried = []
    for src in NOAPI_SOURCES:
        src = src.lower()
        if src not in ("ytsearch", "ytmusicsearch", "scsearch"):
            continue
        tried.append(src)
        items = yt_dlp_search(query, max_results=max_results, source=src)
        # normalizar títulos para filtrar un poco por similitud
        items = [it for it in items if _title_similarity(
            title, it["title"]) >= 0.45]
        if items:
            all_items.extend(items)
            break  # nos quedamos con la primera fuente que devolvió algo
    if tried:
        print(
            f"   🔎 no_api fuentes probadas: {tried} -> {len(all_items)} items")
    return all_items[:max_results]


def _has_artist_signal(artist: str, title_text: str, channel: str, desc: str) -> bool:
    a = _simp_text(artist)
    if not a:
        return False
    s_title = _simp_text(title_text)
    s_ch = _simp_text(channel)
    s_desc = _simp_text(desc)
    return (a in s_title) or (a in s_ch) or (a in s_desc)


def _channel_official_match_strength(artist: str, channel: str, is_official_like: bool) -> float:
    ch = (_simp_text(channel) or "")
    art = (_simp_text(artist) or "")
    score = 0.0
    if is_official_like:
        score += 4.0
    if art and art in ch:
        score += 2.0
    art_first = art.split()[0] if art else ""
    if art_first and art_first in ch:
        score += 1.0
    if re.search(r"\b(oficial|official)\b", ch):
        score += 2.0
    if re.search(r"\b(salsa|radio|esquina|para todos|mix|hits|records|tv|canal|music channel)\b", ch):
        score -= 1.5
    return score


def _structural_match_bonus(artist: str, title: str, raw_title: str) -> float:
    rt = _simp_text(raw_title).replace(
        " — ", " - ").replace("–", "-").replace("—", "-")
    a = _simp_text(artist)
    t = _simp_text(title)
    if f"{a} - {t}" in rt or f"{t} - {a}" in rt:
        return 3.0
    at_tokens = set((a + " " + t).split())
    rt_tokens = set(rt.split())
    inter = len(at_tokens & rt_tokens)
    if inter >= max(2, int(0.6*len(at_tokens))):
        return 1.2
    return 0.0

# ========= Elección de candidato =========


def choose_best_candidate(cands: List[Dict], artist: str, title: str) -> Optional[Dict]:
    if not cands:
        return None

    MIN_TITLE_SIM = 0.62
    title_keys = _key_tokens(title)

    def _title_ok(cand_title: str) -> bool:
        sim = _title_similarity(title, cand_title)
        cand_tokens = set(_simp_text(cand_title).split())
        has_key_overlap = len(title_keys & cand_tokens) >= 1
        return sim >= MIN_TITLE_SIM and has_key_overlap

    # Si vienen desde canal oficial (API), exigir match fuerte de título
    if any(c.get("_official_channel") for c in cands):
        cands = [c for c in cands if _title_ok(c.get("title", ""))]
        if cands:
            print("   ✅ Selección directa desde canal oficial (match fuerte de título).")
            cands.sort(key=lambda x: (int(x.get("views", 0)), -
                       int(x.get("_rank", 9999))), reverse=True)
            return cands[0]

    best, best_score = None, -1e9
    MIN_SCORE = 3.0

    for c in cands:
        raw_title = c.get("title", "")
        ch = c.get("channel_title_full") or c.get("channel", "") or ""
        desc = c.get("description", "") or ""
        ch_desc = c.get("channel_desc", "") or ""
        dur = int(c.get("duration_sec") or 0)
        views = int(c.get("views") or 0)
        rank = int(c.get("_rank") or 9999)
        subs = int(c.get("channel_subs") or 0)
        from_noapi = bool(c.get("_noapi"))

        official_like = _score_channel_officiality(
            artist, ch) >= 3.0 or ch.endswith(" - Topic")

        # HARD GATE artista (excepto Topic). En no_api somos más permisivos si el título es muy bueno.
        has_artist = _has_artist_signal(artist, raw_title, ch, desc)
        if not official_like and not has_artist:
            if from_noapi and _title_similarity(title, raw_title) >= 0.75:
                pass  # permitir si el título matchea fuerte
            else:
                print(
                    f"   ⛔ DESCARTADO por no contener artista → {raw_title} | ch:{ch}")
                continue

        # HARD GATE título
        if not from_noapi and not _title_ok(raw_title):
            print(f"   ⛔ DESCARTADO por bajo match de título → '{raw_title}'")
            continue
        # En no_api relajamos un poco: exigimos sim >= 0.5
        if from_noapi and _title_similarity(title, raw_title) < 0.5:
            print(
                f"   ⛔ (no_api) descarta por similitud insuficiente → '{raw_title}'")
            continue

        if MAKING_BAD_PAT.search(raw_title) or MAKING_BAD_PAT.search(desc):
            print(
                f"   ⛔ DESCARTADO (making-of/documental/ensayo) → {raw_title}")
            continue

        # Validación de canal no-oficial con subs: solo aplica cuando venimos de API
        if not official_like and not from_noapi:
            if not _channel_seems_salsa(ch, ch_desc) or subs < MIN_SUBS_FOR_GENERIC_CHANNEL:
                print(
                    f"   ⛔ DESCARTADO canal débil (no-oficial): subs={subs}, ch='{ch}'")
                continue

        # Scoring
        sim = _title_similarity(title, raw_title)
        score = 4.0*sim
        score += _structural_match_bonus(artist, title, raw_title)

        ct = _normalize_text(raw_title)
        a = _normalize_text(artist)
        t = _normalize_text(title)
        if a and any(x in ct for x in a.split()):
            score += 0.8
        if t and any(x in ct for x in t.split()):
            score += 1.0
        if a and a in ct:
            score += 0.6
        if t and t in ct:
            score += 0.8

        if STUDIO_GOOD_PAT.search(raw_title) or STUDIO_GOOD_PAT.search(desc):
            score += 1.2
        if ch.endswith(" - Topic"):
            score += 1.2
        if "provided to youtube by" in desc.lower():
            score += 1.0

        if LIVE_BAD_PAT.search(raw_title) or LIVE_BAD_PAT.search(desc):
            score -= 4.0
        if FULL_ALBUM_BAD_PAT.search(raw_title) or FULL_ALBUM_BAD_PAT.search(desc):
            score -= 3.0
        if LYRICS_BAD_PAT.search(raw_title) or LYRICS_BAD_PAT.search(desc):
            score -= 2.5
        if MIX_BAD_PAT.search(raw_title) or MIX_BAD_PAT.search(desc):
            score -= 2.0
        if CONTEXT_BAD_PAT.search(raw_title) or CONTEXT_BAD_PAT.search(desc):
            score -= 3.0
        if SERIES_BAD_PAT.search(raw_title) or SERIES_BAD_PAT.search(desc):
            score -= 2.0
        if COMPILATION_BAD_PAT.search(raw_title) or COMPILATION_BAD_PAT.search(desc):
            score -= 1.8

        if dur > 0:
            if dur < 90 or dur > 540:
                score -= 1.8
            else:
                score += 0.4

        score += 0.6 * math.log10(max(1, views))
        if rank == 1:
            score += 0.8
        elif rank == 2:
            score += 0.5
        elif rank == 3:
            score += 0.3

        score += _channel_official_match_strength(
            artist, ch, official_like) * 0.6

        print(
            f"   · candidato: {raw_title} | ch:{ch} | score:{score:.2f} | dur:{dur}s | views:{views} | rank:{rank} | subs:{subs} | no_api:{from_noapi}")
        if score > best_score:
            best, best_score = c, score

    if best:
        if best_score < MIN_SCORE:
            print(
                f"   ❌ Mejor candidato insuficiente [{best_score:.2f}] → sin match")
            return None
        print(
            f"   ✅ Candidato elegido: {best['title']} ({best['video_id']})  [{best_score:.2f}]")
    return best


# ========= Title Case (metadata + filename) =========
LOWER_EXCEPTIONS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "u", "en", "con", "por", "para",
    "a", "al", "un", "una", "uno", "unos", "unas", "the", "of", "and", "feat.", "ft."
}


def _normalize_spaces(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", " ", s.strip())
    return s


def title_case_keep_caps(text: str) -> str:
    text = _normalize_spaces(text)
    if not text:
        return text
    parts = text.split(" ")
    out = []
    for i, w in enumerate(parts):
        if not w:
            out.append(w)
            continue
        w_clean = w.strip()
        if w_clean.isupper() and 2 <= len(w_clean) <= 4:
            out.append(w_clean)
            continue
        base = w_clean.lower()
        if i > 0 and base in LOWER_EXCEPTIONS:
            out.append(base)
        else:
            out.append(base[:1].upper() + base[1:])
    return " ".join(out)

# ========= Ejecutar descarga =========


def run_download(video_id: str, artist: str, title: str, slug: str, image_type: str = "hq"):
    artist = title_case_keep_caps(artist)
    title = title_case_keep_caps(title)
    command = GENRE_COMMAND[slug]
    cmd = f'source {shlex.quote(DL_SCRIPT)} && {command} "{video_id}" "{artist}" "{title}" {image_type}'
    print(
        f"   ⬇️ Ejecutando: {command} {video_id} … artist: {artist} title: {title}")
    return subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)

# ========= Proceso CSV =========


def process_csv(input_csv: str, out_csv: str, dry_run: bool = False, image_type: str = "hq", sleep_s: float = 0.6):
    print(f"📂 Abriendo CSV de entrada: {input_csv}")
    print(f"🧾 Manifest: {MANIFEST_FILE}")
    ensure_manifest(MANIFEST_FILE)
    manifest_keys = load_manifest_keys(MANIFEST_FILE)
    print(f"   ✅ {len(manifest_keys)} entradas en manifest (artist|title).")

    lib_index = build_library_index(LIB_BASE_DIR)

    total_rows = 0
    with open(input_csv, encoding="utf-8") as f:
        total_rows = max(sum(1 for _ in f) - 1, 0)
    print(f"🧾 Filas (sin header): {total_rows}")

    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)

    with open(input_csv, newline="", encoding="utf-8") as f_in, open(out_csv, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        cols = ["artist", "title", "query_used", "video_id", "predicted_genre", "confidence", "rationale",
                "command", "status", "stdout_tail", "stderr_tail", "filepath_hint", "yt_quota_units", "yt_calls_json"]
        writer = csv.DictWriter(f_out, fieldnames=cols)
        writer.writeheader()
        seen = set()
        downloaded = skipped = errors = 0

        for idx, row in enumerate(reader, 1):
            per_track = _new_track_meter()
            try:
                artist = (row.get("artist") or "").strip()
                title = (row.get("title") or "").strip()
                q_override = (row.get("query_override") or "").strip()
                print(f"\n——— [{idx}/{total_rows}] {artist} — {title} ———")
                print(
                    f"   💳 Presupuesto restante antes de esta pista: {_budget_left()}u")

                if not artist or not title:
                    print("   ⚠️ Fila incompleta, saltando.")
                    skipped += 1
                    continue

                key_csv = (artist.lower(), title.lower())
                if key_csv in seen:
                    print("   ↩️ Duplicado en CSV, saltando.")
                    skipped += 1
                    continue
                seen.add(key_csv)

                nk = norm_key(artist, title)
                if nk in manifest_keys:
                    print("   ⏭️ Ya está en manifest → skip.")
                    writer.writerow({
                        "artist": artist, "title": title, "query_used": q_override or f"{artist} {title}",
                        "video_id": "", "predicted_genre": "", "confidence": 1.0,
                        "rationale": "skip: manifest (artist-title ya registrado)",
                        "command": "", "status": "skipped(manifest)",
                        "stdout_tail": "", "stderr_tail": "", "filepath_hint": "",
                        "yt_quota_units": per_track["quota_units"], "yt_calls_json": json.dumps(per_track["api_calls"])
                    })
                    skipped += 1
                    continue

                if nk in lib_index:
                    print("   ⏭️ Ya existe en librería → skip.")
                    writer.writerow({
                        "artist": artist, "title": title, "query_used": q_override or f"{artist} {title}",
                        "video_id": "", "predicted_genre": "", "confidence": 1.0,
                        "rationale": "skip: archivo ya existe (artist-title)",
                        "command": "", "status": "skipped(already_exists)",
                        "stdout_tail": "", "stderr_tail": "", "filepath_hint": "",
                        "yt_quota_units": per_track["quota_units"], "yt_calls_json": json.dumps(per_track["api_calls"])
                    })
                    skipped += 1
                    continue

                # === Resolver video_id ===
                vid_override = extract_video_id(
                    q_override) if q_override else None
                if vid_override:
                    video_id = vid_override
                    used_query = f"ID directo: {video_id}"
                    print(
                        f"   🔗 Usando VIDEO_ID directo desde override: {video_id}")
                    best_meta = {"title": title, "artist": artist,
                                 "description": "", "channel": ""}

                else:
                    # Selector según SEARCH_MODE y presupuesto
                    def _try_noapi():
                        return find_candidates_noapi(artist, title, max_results=YOUTUBE_MAX_RESULTS)

                    def _try_api():
                        base_query = f'"{artist} {title}"'
                        return search_youtube_id(base_query, max_results=YOUTUBE_MAX_RESULTS, artist_hint=artist, title_hint=title, per_track=per_track)

                    cands: List[Dict] = []
                    used_query = f"{artist} {title}"

                    if SEARCH_MODE == "no_api_only":
                        print("   🌐 Modo búsqueda: NO_API_ONLY")
                        cands = _try_noapi()

                    elif SEARCH_MODE == "api_only":
                        print("   🌐 Modo búsqueda: API_ONLY")
                        if _budget_left() <= 0:
                            print(
                                "   ⛔ Presupuesto API agotado, sin fallback por configuración.")
                            cands = []
                        else:
                            cands = _try_api()

                    elif SEARCH_MODE == "api_first":
                        print("   🌐 Modo búsqueda: API_FIRST")
                        if _budget_left() > 0:
                            cands = _try_api()
                        if not cands:
                            print("   ↪️ Fallback a NO_API...")
                            cands = _try_noapi()

                    else:
                        # no_api_first (default)
                        print("   🌐 Modo búsqueda: NO_API_FIRST")
                        cands = _try_noapi()
                        if not cands:
                            if _budget_left() > 0:
                                print("   ↪️ Fallback a API...")
                                cands = _try_api()
                            else:
                                print(
                                    "   ⛔ Sin resultados NO_API y presupuesto API agotado.")
                                cands = []

                    best = choose_best_candidate(cands, artist, title)
                    if not best:
                        print("   ❌ Sin resultados adecuados.")
                        writer.writerow({
                            "artist": artist, "title": title, "query_used": used_query,
                            "video_id": "", "predicted_genre": "", "confidence": 0,
                            "rationale": "sin resultados", "command": "", "status": "no_match",
                            "stdout_tail": "", "stderr_tail": "", "filepath_hint": "",
                            "yt_quota_units": per_track["quota_units"], "yt_calls_json": json.dumps(per_track["api_calls"])
                        })
                        skipped += 1
                        continue

                    video_id = best["video_id"]
                    best_meta = {"title": title, "artist": artist, "description": best.get(
                        "description", ""), "channel": best.get("channel_title_full", best.get("channel", ""))}

                print(
                    f"   💳 Cuota gastada en esta pista (antes de clasif/descarga): {per_track['quota_units']}u | llamadas: {per_track['api_calls']}")

                # Clasificar
                cls = classify(best_meta)
                print(f"   🎯 Género: {cls['slug']} ({cls['confidence']})")

                # Descargar
                status, stdout_tail, stderr_tail, filepath_hint = "skipped(dryrun)", "", "", ""
                if not dry_run:
                    r = run_download(video_id, artist, title,
                                     cls["slug"], image_type=image_type)
                    status = "downloaded" if r.returncode == 0 else f"error({r.returncode})"
                    stdout_tail, stderr_tail = (
                        r.stdout or "")[-300:], (r.stderr or "")[-300:]
                    print(f"   📦 Resultado descarga: {status}")

                    if status != "downloaded":
                        # Diagnóstico adicional
                        try:
                            print("   🧪 Debug descarga:")
                            print(f"      PATH= {os.getenv('PATH', '')}")
                            import shutil as _sh
                            print(
                                f"      which yt-dlp = {_sh.which('yt-dlp')}")
                            print(
                                f"      which ffmpeg = {_sh.which('ffmpeg')}")
                            # Verificar que la función bash exista tras source
                            cmd_name = cls.get("command", "")
                            check = subprocess.run([
                                "bash", "-lc",
                                f"source {shlex.quote(DL_SCRIPT)} >/dev/null 2>&1 && type -t {shlex.quote(cmd_name)} || true"
                            ], capture_output=True, text=True)
                            out = (check.stdout or "" +
                                   check.stderr or "").strip()
                            print(
                                f"      type -t {cmd_name} -> {out or '(sin salida)'}")
                            if stdout_tail:
                                print(f"      stdout_tail: {stdout_tail}")
                            if stderr_tail:
                                print(f"      stderr_tail: {stderr_tail}")
                        except Exception as _e:
                            print(f"      (debug falló) {_e}")

                    if status == "downloaded":
                        subdir = cls["command"].split(
                            "dl-")[-1].replace("-", "_")
                        filepath_hint = f"{LIB_BASE_DIR}/{subdir}/{title_case_keep_caps(artist)} - {title_case_keep_caps(title)}.mp3"
                        append_manifest_row(
                            MANIFEST_FILE, artist, title, video_id, cls["slug"], cls["command"], status, filepath_hint)
                        downloaded += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

                writer.writerow({
                    "artist": artist, "title": title, "query_used": used_query,
                    "video_id": video_id, "predicted_genre": cls["slug"], "confidence": cls["confidence"],
                    "rationale": cls["rationale"], "command": cls["command"], "status": status,
                    "stdout_tail": stdout_tail, "stderr_tail": stderr_tail, "filepath_hint": filepath_hint,
                    "yt_quota_units": per_track["quota_units"], "yt_calls_json": json.dumps(per_track["api_calls"])
                })

                print(
                    f"   ✅ Cuota final por pista: {per_track['quota_units']}u | llamadas: {per_track['api_calls']}")
                time.sleep(sleep_s)

            except Exception:
                print("   💥 Error procesando fila:")
                traceback.print_exc()
                errors += 1

    print(f"\n✅ Terminado. Descargadas: {downloaded} | Skips: {skipped}")
    _print_totals()
    print(f"📝 Log en: {out_csv}")


def extract_video_id(s: Optional[str]) -> Optional[str]:
    """Extrae el ID de YouTube (11 chars) desde un ID directo o una URL."""
    if not s:
        return None
    s = s.strip()
    if VIDEO_ID_RE.fullmatch(s):
        return s
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    m = re.search(r"/embed/([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    return None


# ========= CLI =========
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline CSV -> YouTube -> Clasifica 16 géneros -> Descarga (manifest + override-ID)")
    parser.add_argument("--input", required=True,
                        help="CSV con columnas: artist,title[,query_override]")
    parser.add_argument(
        "--output", default="out/log_descargas.csv", help="CSV de salida")
    parser.add_argument("--dry-run", action="store_true",
                        help="No descarga, solo busca y clasifica")
    parser.add_argument("--image-type", default="hq",
                        choices=["hq", "max"], help="thumbnail type (pasa al bash)")
    args = parser.parse_args()

    if not os.path.exists(DL_SCRIPT):
        raise SystemExit("DL_MUSIC_SCRIPT no existe o no está seteado")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    process_csv(args.input, args.output, dry_run=args.dry_run,
                image_type=args.image_type)
