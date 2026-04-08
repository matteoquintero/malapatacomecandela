# mpc/acquisition/engine.py
# -*- coding: utf-8 -*-
"""
DownloadEngine: orquestador del pipeline de adquisición (BC Acquisition).

Responsabilidades:
  1. build_steps() → construye la secuencia de steps según la configuración.
  2. process()     → ejecuta los steps secuencialmente sobre un contexto mutable.
  3. process_batch() → procesa una lista de DownloadRequest.
  4. process_csv() → lee un CSV de entrada, delega a process_batch, escribe log CSV.

Principios:
  - Cada step es independiente y testeable.
  - El contexto (ctx) viaja mutable por todos los steps.
  - Un step puede cortocircuitar el pipeline seteando ctx["skip"]=True.
  - No hay estado global; toda la config viene de DownloadConfig.
  - La persistencia se delega a TrackRepository (BC Library).
"""

import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from mpc.catalog.genres import GENRE_COMMAND, BLOCKED_ARTISTS, BLOCKED_GENRES
from mpc.acquisition.request import DownloadRequest
from mpc.acquisition.result import DownloadError, DownloadResult, DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.acquisition.steps.classifier import GenreClassifierStep
from mpc.acquisition.steps.downloader import DownloaderStep, SpotdlDownloader, YtDlpDownloader
from mpc.acquisition.steps.idempotency import IdempotencyStep
from mpc.acquisition.steps.scorer import CandidateScorerStep
from mpc.acquisition.steps.search_noapi import NoApiSearchStep
from mpc.acquisition.track_ref import SPOTIFY, TrackRef, infer_platform, youtube_ref
from mpc.library.repository import TrackRepository
from mpc.library.index import LibraryIndex
from mpc.utils.text import simp_pipeline as _simp_text

logger = logging.getLogger("mpc.acquisition.engine")

# Columnas del log CSV de salida
_LOG_CSV_COLS = [
    "artist", "title", "query_used", "video_id", "platform", "predicted_genre",
    "confidence", "rationale", "command", "status",
    "stderr_tail", "filepath_hint",
]


@dataclass
class DownloadConfig:
    # Rutas
    lib_base_dir: str
    manifest_path: str     # legacy CSV path (para migración); nuevo: db_path
    db_path: str = ""      # SQLite library path; si vacío usa manifest_path.replace('.csv','.db')

    # Búsqueda (yt-dlp, sin API — escalable a cualquier fuente que soporte yt-dlp)
    search_sources: List[str] = field(default_factory=lambda: ["ytsearch", "scsearch"])
    ytdlp_bin: str = "yt-dlp"
    spotdl_bin: str = "spotdl"
    max_search_results: int = 5

    # Clasificador
    classifier_mode: str = "LLM_FALLBACK"   # HEURISTIC_ONLY | LLM_FALLBACK | LLM_ONLY
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Pausa entre canciones (segundos)
    sleep_between: float = 0.5

    def resolved_db_path(self) -> str:
        if self.db_path:
            return self.db_path
        return self.manifest_path.replace(".csv", ".db")

    @classmethod
    def from_env(cls) -> "DownloadConfig":
        """Construye la config desde variables de entorno."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        manifest = os.getenv("MANIFEST_FILE", os.path.join(os.getcwd(), "cache/manifest.csv"))
        return cls(
            lib_base_dir=os.getenv("LIB_BASE_DIR", os.path.expanduser("~/Music/mala_pata_come_candela")),
            manifest_path=manifest,
            db_path=os.getenv("LIBRARY_DB", manifest.replace(".csv", ".db")),
            search_sources=[s.strip() for s in os.getenv("SEARCH_SOURCES", "ytsearch,scsearch").split(",") if s.strip()],
            ytdlp_bin=os.getenv("YTDLP_BIN", "yt-dlp"),
            spotdl_bin=os.getenv("SPOTDL_BIN", "spotdl"),
            max_search_results=int(os.getenv("MAX_SEARCH_RESULTS", "5")),
            classifier_mode=os.getenv("CLASSIFIER_MODE", "LLM_FALLBACK"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )


def _print_result(r: "DownloadResult") -> None:
    """Imprime en stdout el resultado de una canción (solo para estados no impresos antes)."""
    s = r.status
    src = r.platform or "?"
    genre = r.genre_slug or "?"
    vid = r.video_id or "sin ID"
    if s == DownloadStatus.DOWNLOADED:
        print(f"   ✅ {src} → {genre}  [{vid}]")
    elif s in (DownloadStatus.SKIPPED_MANIFEST, DownloadStatus.SKIPPED_EXISTS):
        pass  # ya impreso por el cortocircuito de IdempotencyStep
    elif s == DownloadStatus.DRY_RUN:
        print(f"   🧪 Dry-run  {src} → {genre}  [{vid}]")
    elif s == DownloadStatus.NO_MATCH:
        print(f"   ❌ Sin coincidencia: {r.rationale or r.error_detail or ''}")
    elif s == DownloadStatus.DOWNLOAD_ERROR:
        print(f"   ❌ Error ({src}): {r.error_detail or r.error or ''}")
    elif s == DownloadStatus.SKIPPED_CSV_DUP:
        print("   ↩️  Duplicado en CSV → skip")
    else:
        print(f"   ⚠️  {s.value}: {r.error_detail or r.rationale or ''}")


def _build_lib_index(base_dir: str) -> Set[str]:
    """Indexa la librería en disco: normaliza nombres de MP3 existentes."""
    known: Set[str] = set()
    if not os.path.exists(base_dir):
        return known
    for _, _, files in os.walk(base_dir):
        for fn in files:
            if fn.lower().endswith(".mp3") and " - " in fn:
                name = os.path.splitext(fn)[0]
                artist, _, title = name.partition(" - ")
                known.add(f"{_simp_text(artist)}|{_simp_text(title)}")
    logger.debug("lib_index: %d MP3 indexados", len(known))
    return known


def _build_genres_ref() -> str:
    """Referencia compacta de géneros para el LLM."""
    from mpc.catalog.genres import GENRE_DB
    try:
        ref = [
            {
                "name": g["name"],
                "aliases": g.get("aliases", []),
                "rhythm_traits": g.get("rhythm_traits", []),
                "artists_key": g.get("artists_key", []),
            }
            for g in GENRE_DB
        ]
        return json.dumps({"genres": ref}, ensure_ascii=False)
    except Exception:
        return ""


class DownloadEngine:
    """
    Orquestador del pipeline de adquisición.
    Usa TrackRepository (BC Library) como fuente de verdad de idempotencia.

    Uso típico:
        config = DownloadConfig.from_env()
        engine = DownloadEngine(config)
        engine.process_csv("data/canciones.csv", "out/log.csv")
    """

    def __init__(self, config: DownloadConfig):
        self.config = config
        self._repo = TrackRepository(
            db_path=config.resolved_db_path(),
            legacy_csv=config.manifest_path,   # migra CSV legado si la tabla está vacía
        )
        self._lib_index = _build_lib_index(config.lib_base_dir)
        self._openai_client = self._init_openai()
        self._genres_ref = _build_genres_ref()

    def _init_openai(self) -> Optional[Any]:
        if not self.config.openai_api_key:
            return None
        try:
            from openai import OpenAI
            return OpenAI(api_key=self.config.openai_api_key)
        except Exception as e:
            logger.warning("engine: OpenAI no disponible: %s", e)
            return None

    def build_steps(self) -> List[BaseStep]:
        """
        Construye la secuencia de steps.
        Orden fijo: idempotency → search → score → classify → download.
        """
        cfg = self.config
        ytdlp = YtDlpDownloader(cfg.lib_base_dir, cfg.ytdlp_bin)
        spotdl = SpotdlDownloader(cfg.lib_base_dir, cfg.spotdl_bin)

        return [
            IdempotencyStep(self._repo, self._lib_index),
            NoApiSearchStep(
                ytdlp_bin=cfg.ytdlp_bin,
                sources=cfg.search_sources,
                max_results=cfg.max_search_results,
            ),
            CandidateScorerStep(),
            GenreClassifierStep(
                mode=cfg.classifier_mode,
                openai_client=self._openai_client,
                openai_model=cfg.openai_model,
                genres_ref=self._genres_ref,
            ),
            DownloaderStep(ytdlp, spotdl),
        ]

    def process(self, request: DownloadRequest) -> DownloadResult:
        """Ejecuta el pipeline para un DownloadRequest. Retorna un DownloadResult."""
        ctx: Dict[str, Any] = {
            "request": request,
            "candidates": [],
            "track_ref": None,
            "video_id": None,
            "best_meta": None,
            "genre_slug": "",
            "confidence": 0.0,
            "rationale": "",
            "filepath": "",
            "query_used": f"{request.artist} {request.title}",
            "skip": False,
            "skip_status": None,
            "skip_reason": "",
            "error": None,
            "error_detail": "",
        }

        # Validación: artistas y géneros bloqueados
        artist_simp = _simp_text(request.artist)
        if any(b in artist_simp for b in BLOCKED_ARTISTS):
            print(f"   🚫 Este es un sistema de música afrolatina seria. '{request.artist}' no entra aquí.")
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.DOWNLOAD_ERROR
            ctx["error_detail"] = f"artista bloqueado: {request.artist}"
            return self._build_result(ctx, request)

        if request.genre:
            genre_simp = _simp_text(request.genre)
            if any(b in genre_simp for b in BLOCKED_GENRES):
                print(f"   🚫 '{request.genre}' no es un género de este sistema. Pide algo con alma.")
                ctx["skip"] = True
                ctx["skip_status"] = DownloadStatus.DOWNLOAD_ERROR
                ctx["error_detail"] = f"género bloqueado: {request.genre}"
                return self._build_result(ctx, request)

        # Resolución directa desde query_override
        if request.query_override:
            ref = self._extract_track_ref(request.query_override)
            if ref:
                ctx["track_ref"] = ref
                ctx["video_id"] = ref.display_id
                ctx["query_used"] = f"override ({ref.platform}): {ref.display_id}"
                ctx["best_meta"] = {"title": request.title, "artist": request.artist,
                                    "description": "", "channel": ""}
                print(f"   🎯 Override directo ({ref.platform}): {ref.display_id}")

        steps = self.build_steps()
        for step in steps:
            try:
                step.run(ctx)
            except Exception as e:
                logger.error("engine: step %s error: %s", step.name, e)
                ctx["skip"] = True
                ctx["skip_status"] = DownloadStatus.DOWNLOAD_ERROR
                ctx["error"] = DownloadError.DOWNLOAD_FAILED
                ctx["error_detail"] = str(e)
                break
            if ctx.get("skip") and step.name == "IdempotencyStep":
                if ctx.get("skip_status") == DownloadStatus.SKIPPED_MANIFEST:
                    print("   ⏭️  Ya bendecido (repositorio) → skip")
                elif ctx.get("skip_status") == DownloadStatus.SKIPPED_EXISTS:
                    print("   ⏭️  Ya en el archivo → skip")
                break

        return self._build_result(ctx, request)

    def _build_result(self, ctx: Dict[str, Any], request: DownloadRequest) -> DownloadResult:
        status = self._resolve_status(ctx)
        genre_slug = ctx.get("genre_slug") or ""
        command = GENRE_COMMAND.get(genre_slug, "")
        track_ref: Optional[TrackRef] = ctx.get("track_ref")

        result = DownloadResult(
            artist=request.artist,
            title=request.title,
            status=status,
            video_id=(track_ref.display_id if track_ref else ctx.get("video_id")) or "",
            platform=track_ref.platform if track_ref else "",
            genre_slug=genre_slug,
            confidence=ctx.get("confidence") or 0.0,
            rationale=ctx.get("rationale") or ctx.get("skip_reason") or "",
            filepath=ctx.get("filepath") or "",
            query_used=ctx.get("query_used") or "",
            command=command,
            error=ctx.get("error"),
            error_detail=ctx.get("error_detail") or "",
        )

        if result.status == DownloadStatus.DOWNLOADED and not request.dry_run:
            self._repo.record(
                artist=request.artist,
                title=request.title,
                video_id=result.video_id,
                platform=result.platform,
                genre_slug=result.genre_slug,
                filepath=result.filepath,
                status="downloaded",
                confidence=result.confidence,
            )

        return result

    def process_batch(self, requests: List[DownloadRequest]) -> List[DownloadResult]:
        """Procesa una lista de requests secuencialmente."""
        results = []
        seen_csv: Set[str] = set()
        total = len(requests)

        for i, req in enumerate(requests, 1):
            print(f"\n🎵 [{i}/{total}] {req.artist} — {req.title}")

            key = f"{req.artist.lower()}|{req.title.lower()}"
            if key in seen_csv:
                print("   ↩️  Duplicado en CSV, saltando.")
                results.append(DownloadResult(
                    artist=req.artist, title=req.title,
                    status=DownloadStatus.SKIPPED_CSV_DUP,
                    rationale="Duplicado en CSV",
                ))
                continue
            seen_csv.add(key)

            result = self.process(req)
            results.append(result)
            _print_result(result)

            if self.config.sleep_between > 0:
                time.sleep(self.config.sleep_between)

        downloaded = sum(1 for r in results if r.status == DownloadStatus.DOWNLOADED)
        logger.info("engine: %d descargadas | %d otras", downloaded, len(results) - downloaded)
        return results

    def process_csv(
        self,
        input_csv: str,
        output_csv: str,
        dry_run: bool = False,
        image_type: str = "hq",
        sleep_s: float = 0.6,
    ) -> List[DownloadResult]:
        """
        Lee input_csv (columnas: artist, title, query_override, genre),
        procesa cada fila con el engine, escribe el log a output_csv.
        """
        print(f"La llama se enciende con: {os.path.basename(input_csv)}")

        requests: List[DownloadRequest] = []
        with open(input_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                artist = (row.get("artist") or "").strip()
                title = (row.get("title") or "").strip()
                if not artist or not title:
                    continue
                requests.append(DownloadRequest(
                    artist=artist,
                    title=title,
                    query_override=(row.get("query_override") or "").strip() or None,
                    genre=(row.get("genre") or "").strip() or None,
                    image_type=image_type,
                    dry_run=dry_run,
                ))

        total = len(requests)
        print(f"{total} canciones en el CSV")

        orig_sleep = self.config.sleep_between
        self.config.sleep_between = sleep_s

        results = self.process_batch(requests)

        self.config.sleep_between = orig_sleep

        os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_LOG_CSV_COLS)
            writer.writeheader()
            for r in results:
                writer.writerow(r.to_csv_row())

        downloaded = sum(1 for r in results if r.status == DownloadStatus.DOWNLOADED)
        skipped = len(results) - downloaded

        # Resumen desde Library
        idx = LibraryIndex(self._repo)
        summary = idx.summary()
        print(f"\n{downloaded} bendiciones | {skipped} ya consagradas")
        logger.debug("Log detallado en: %s | Library summary: %s", output_csv, summary)

        return results

    @staticmethod
    def _extract_track_ref(s: str) -> Optional[TrackRef]:
        """
        Convierte query_override en TrackRef.
        Soporta: YouTube ID, YouTube URL, Spotify URI/URL, SoundCloud URL, URL genérica.
        """
        s = (s or "").strip()
        if not s:
            return None

        if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
            return youtube_ref(s)

        for pat in (r"[?&]v=([A-Za-z0-9_-]{11})", r"youtu\.be/([A-Za-z0-9_-]{11})",
                    r"/embed/([A-Za-z0-9_-]{11})"):
            m = re.search(pat, s)
            if m:
                return youtube_ref(m.group(1))

        if s.startswith("spotify:"):
            display_id = s.rsplit(":", 1)[-1] or s
            return TrackRef(url=s, platform=SPOTIFY, display_id=display_id, thumbnail_url="")

        if s.startswith(("http://", "https://")):
            platform = infer_platform(s)
            display_id = s.rstrip("/").rsplit("/", 1)[-1] or s
            return TrackRef(url=s, platform=platform, display_id=display_id, thumbnail_url="")

        return None

    @staticmethod
    def _resolve_status(ctx: Dict[str, Any]) -> DownloadStatus:
        if ctx.get("status_override"):
            return ctx["status_override"]
        if ctx.get("skip_status"):
            return ctx["skip_status"]
        if ctx.get("download_status"):
            return ctx["download_status"]
        return DownloadStatus.DOWNLOAD_ERROR
