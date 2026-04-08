# pipeline_music.py
# -*- coding: utf-8 -*-
# ─── mpc path ────────────────────────────────────────────────────────────────
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
# ─────────────────────────────────────────────────────────────────────────────
"""
Pipeline CSV → búsqueda yt-dlp → clasificación → descarga MP3

Uso:
    python scripts/pipeline_music.py --input data/canciones.csv --output out/log.csv
    python scripts/pipeline_music.py --input data/canciones.csv --dry-run

Variables de entorno (.env):
    LIB_BASE_DIR     Directorio raíz de la librería (default: ~/Music/mala_pata_come_candela)
    MANIFEST_FILE    Ruta del manifest de descargas (default: cache/manifest.csv)
    SEARCH_SOURCES   Fuentes yt-dlp separadas por coma (default: ytsearch,scsearch)
    YTDLP_BIN        Binario de yt-dlp (default: yt-dlp)
    MAX_SEARCH_RESULTS Máximo de resultados por búsqueda (default: 5)
    CLASSIFIER_MODE  HEURISTIC_ONLY | LLM_FALLBACK | LLM_ONLY (default: LLM_FALLBACK)
    OPENAI_API_KEY   Clave OpenAI (solo para LLM_FALLBACK/LLM_ONLY)
    OPENAI_MODEL     Modelo OpenAI (default: gpt-4o-mini)
    DEBUG_MODE       true/false — imprime config al inicio (default: false)
"""

import argparse
import os

# ── .env ──────────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("true", "1", "yes", "on")
    def debug_print(*a, **k):
        if DEBUG_MODE:
            print(*a, **k)
    debug_print("🧩 .env cargado.")
except Exception:
    DEBUG_MODE = False
    def debug_print(*a, **k): pass

# ── Config ────────────────────────────────────────────────────────────────────
LIB_BASE_DIR   = os.getenv("LIB_BASE_DIR", os.path.expanduser("~/Music/mala_pata_come_candela"))
MANIFEST_FILE  = os.getenv("MANIFEST_FILE", os.path.join(PROJECT_DIR, "cache/manifest.csv"))
CLASSIFIER_MODE = os.getenv("CLASSIFIER_MODE", "LLM_FALLBACK")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SEARCH_SOURCES  = [s.strip() for s in os.getenv("SEARCH_SOURCES", "ytsearch,scsearch").split(",") if s.strip()]
YTDLP_BIN       = os.getenv("YTDLP_BIN", "yt-dlp")
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
DL_SCRIPT       = os.getenv("DL_MUSIC_SCRIPT", os.path.join(PROJECT_DIR, "dl-music-system.sh"))

# Compat: manifest legado
try:
    _old = os.path.expanduser("~/.mala_pata/manifest.csv")
    if "MANIFEST_FILE" not in os.environ and os.path.exists(_old):
        MANIFEST_FILE = _old
        debug_print(f"ℹ️ Manifest heredado: {_old}")
except Exception:
    pass

debug_print("⚙️ Config:")
debug_print(f"   LIB_BASE_DIR      = {LIB_BASE_DIR}")
debug_print(f"   MANIFEST_FILE     = {MANIFEST_FILE}")
debug_print(f"   SEARCH_SOURCES    = {SEARCH_SOURCES}")
debug_print(f"   MAX_SEARCH_RESULTS= {MAX_SEARCH_RESULTS}")
debug_print(f"   CLASSIFIER_MODE   = {CLASSIFIER_MODE}")
debug_print(f"   OPENAI_MODEL      = {OPENAI_MODEL}")
debug_print(f"   YTDLP_BIN         = {YTDLP_BIN}")


# ── Pipeline ──────────────────────────────────────────────────────────────────
def process_csv(input_csv: str, out_csv: str, dry_run: bool = False,
                image_type: str = "hq", sleep_s: float = 0.6):
    """Thin wrapper: delega al DownloadEngine en mpc/download/."""
    from mpc.acquisition.engine import DownloadConfig, DownloadEngine
    cfg = DownloadConfig(
        lib_base_dir=LIB_BASE_DIR,
        manifest_path=MANIFEST_FILE,
        search_sources=SEARCH_SOURCES,
        ytdlp_bin=YTDLP_BIN,
        max_search_results=MAX_SEARCH_RESULTS,
        classifier_mode=CLASSIFIER_MODE,
        openai_api_key=OPENAI_API_KEY,
        openai_model=OPENAI_MODEL,
    )
    engine = DownloadEngine(cfg)
    engine.process_csv(input_csv, out_csv, dry_run=dry_run,
                       image_type=image_type, sleep_s=sleep_s)


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline CSV -> búsqueda yt-dlp -> clasifica 16 géneros -> descarga MP3")
    parser.add_argument("--input",  required=True, help="CSV: artist,title[,query_override,genre]")
    parser.add_argument("--output", default="out/log_descargas.csv", help="CSV de log de salida")
    parser.add_argument("--dry-run", action="store_true", help="Solo busca y clasifica, no descarga")
    parser.add_argument("--image-type", default="hq", choices=["hq", "max"],
                        help="Calidad del thumbnail")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    process_csv(args.input, args.output, dry_run=args.dry_run, image_type=args.image_type)
