# mpc/config.py
# -*- coding: utf-8 -*-
"""
Configuración centralizada. Lee .env una sola vez.
Todos los módulos importan Config en lugar de llamar os.getenv directamente.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

PROJECT_DIR = Path(__file__).parent.parent.resolve()

logger = logging.getLogger("mpc.config")


def setup_logging(verbose: int = 0):
    """
    verbose=0 → WARNING (solo errores visibles al usuario)
    verbose=1 → INFO  (operaciones normales)
    verbose=2 → DEBUG (detalle máximo, equivalente al antiguo DEBUG_MODE)
    """
    level = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}.get(verbose, logging.INFO)
    logging.basicConfig(
        format="%(levelname)s [%(name)s] %(message)s",
        level=level,
    )
    # Silenciar loggers ruidosos de terceros
    for noisy in ("urllib3", "httpx", "httpcore", "spotipy", "googleapiclient"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@dataclass
class Config:
    # ── APIs ──────────────────────────────────────────────────────────────────
    youtube_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    discogs_token: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "https://localhost:8080/callback"
    spotify_token_cache: str = ""

    # ── Rutas ─────────────────────────────────────────────────────────────────
    dl_music_script: str = ""
    lib_base_dir: str = ""
    manifest_file: str = ""
    channel_cache_file: str = ""
    search_cache_file: str = ""
    genre_ref_path: str = ""

    # ── Búsqueda ─────────────────────────────────────────────────────────────
    search_mode: str = "no_api_first"
    noapi_sources: List[str] = field(default_factory=lambda: ["ytsearch", "scsearch"])
    ytdlp_bin: str = "yt-dlp"
    disable_api_fallback: bool = False
    youtube_max_results: int = 5
    youtube_call_budget: int = 4_000_000
    channel_cache_ttl_days: int = 30
    search_cache_ttl_days: int = 45
    min_subs_generic_channel: int = 30_000

    # ── Clasificador ─────────────────────────────────────────────────────────
    classifier_mode: str = "LLM_FALLBACK"   # LLM_FALLBACK | HEURISTIC_ONLY | LLM_ONLY
    pass_heuristic_to_llm: bool = False
    low_conf_threshold: float = 0.80

    # ── Debug ─────────────────────────────────────────────────────────────────
    debug: bool = False

    # ── CSV de entrada/salida ────────────────────────────────────────────────
    default_csv: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        try:
            from dotenv import load_dotenv
            load_dotenv(PROJECT_DIR / ".env")
        except ImportError:
            pass

        def _p(key: str, default: str) -> str:
            return os.getenv(key, default)

        def _bool(key: str, default: bool) -> bool:
            v = os.getenv(key, "").lower()
            if not v:
                return default
            return v in ("true", "1", "yes", "on")

        def _int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except (ValueError, TypeError):
                return default

        cache_dir = str(PROJECT_DIR / "cache")
        return cls(
            youtube_api_key=_p("YOUTUBE_API_KEY", ""),
            openai_api_key=_p("OPENAI_API_KEY", ""),
            openai_model=_p("OPENAI_MODEL", "gpt-4o-mini"),
            discogs_token=_p("DISCOGS_TOKEN", ""),
            spotify_client_id=_p("SPOTIFY_CLIENT_ID", ""),
            spotify_client_secret=_p("SPOTIFY_CLIENT_SECRET", ""),
            spotify_redirect_uri=_p("SPOTIFY_REDIRECT_URI", "https://localhost:8080/callback"),
            spotify_token_cache=_p("SPOTIFY_TOKEN_CACHE", str(PROJECT_DIR / "cache/spotify_token_cache")),

            dl_music_script=_p("DL_MUSIC_SCRIPT", str(PROJECT_DIR / "dl-music-system.sh")),
            lib_base_dir=_p("LIB_BASE_DIR", str(Path.home() / "Music/mala_pata_come_candela")),
            manifest_file=_p("MANIFEST_FILE", f"{cache_dir}/manifest.csv"),
            channel_cache_file=_p("CHANNEL_CACHE_FILE", f"{cache_dir}/yt_channel_cache.json"),
            search_cache_file=_p("SEARCH_CACHE_FILE", f"{cache_dir}/yt_search_cache.json"),
            genre_ref_path=_p("GENRE_REF_PATH", ""),

            search_mode=_p("SEARCH_MODE", "no_api_first").strip().lower(),
            noapi_sources=[s.strip() for s in _p("NOAPI_SOURCES", "ytsearch,scsearch").split(",") if s.strip()],
            ytdlp_bin=_p("YTDLP_BIN", "yt-dlp"),
            disable_api_fallback=_bool("DISABLE_API_FALLBACK", False),
            youtube_max_results=_int("YOUTUBE_MAX_RESULTS", 5),
            youtube_call_budget=_int("YOUTUBE_CALL_BUDGET", 4_000_000),
            channel_cache_ttl_days=_int("CHANNEL_CACHE_TTL_DAYS", 30),
            search_cache_ttl_days=_int("SEARCH_CACHE_TTL_DAYS", 45),
            min_subs_generic_channel=_int("MIN_SUBS_FOR_GENERIC_CHANNEL", 30_000),

            classifier_mode=_p("CLASSIFIER_MODE", "LLM_FALLBACK"),
            pass_heuristic_to_llm=_bool("PASS_HEURISTIC_TO_LLM", False),
            low_conf_threshold=float(_p("LOW_CONF_THRESHOLD", "0.80")),

            debug=_bool("DEBUG_MODE", False),
            default_csv=_p("DEFAULT_CSV", str(PROJECT_DIR / "canciones.csv")),
        )

    def validate(self):
        """Valida configuración crítica al arranque. Lanza ValueError con mensaje claro."""
        errors = []

        dl = self.dl_music_script
        if not dl or not os.path.exists(dl):
            errors.append(f"DL_MUSIC_SCRIPT no encontrado: '{dl}' — revisa .env")

        if errors:
            msg = "\n".join(f"  ✗ {e}" for e in errors)
            raise ValueError(f"Errores de configuración:\n{msg}")

    def validate_for_download(self):
        """Validación extra para el subcomando download."""
        self.validate()
        if not self.lib_base_dir:
            raise ValueError("LIB_BASE_DIR no está configurado en .env")


# Singleton de configuración (lazy, se carga la primera vez que se importa)
_cfg: Optional[Config] = None


def get_config() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = Config.from_env()
    return _cfg
