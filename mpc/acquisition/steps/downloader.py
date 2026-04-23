# mpc/download/steps/downloader.py
# -*- coding: utf-8 -*-
"""
YtDlpDownloader: descarga MP3 desde YouTube usando yt-dlp con múltiples
estrategias de formato, en Python puro.

Reemplaza la función dl_music() de dl-music-system.sh.
Las 7 estrategias de formato son idénticas a las del bash original
para mantener la misma resiliencia frente a SABR streaming.
"""

import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

from mpc.catalog.genres import GENRE_DIR
from mpc.acquisition.result import DownloadError, DownloadStatus
from mpc.acquisition.steps.base import BaseStep
from mpc.acquisition.steps.tagger import MetadataTagger
from mpc.acquisition.track_ref import SPOTIFY, TrackRef
from mpc.utils.text import sanitize_filename, sanitize_filename_component, canonical_filename

logger = logging.getLogger("mpc.acquisition.steps.downloader")

_YTDLP_BASE = ["-x", "--audio-format", "mp3", "--audio-quality", "0"]

# Keywords que indican video NO-oficial (lyric, cover, fan-made) - REJECT
_BAD_VIDEO_KEYWORDS = [
    "lyric", "lyrics",
    " cover ", "cover ", " cover",
    "remix", "remix ",
    " reaction", "reactions", "react ",
    "compilation", " compilation",
]

# Keywords que indican video PREFERRED (official audio, live performance) - ACCEPT
_GOOD_VIDEO_KEYWORDS = [
    "official audio",
    "official video",
    "live performance",
    "audiovisual",
    "in concert",
    "live at",
    "en vivo",
    "concierto",
    "tour",
]

# Keywords ambiguous - ASK USER
_AMBIGUOUS_VIDEO_KEYWORDS = ["live", " en vivo ", " vivo "]


def is_official_video(video_title: str, channel: str = "") -> bool:
    """
    Valida que el video sea oficial, no lyric/cover/fan-made.

    Args:
        video_title: Título del video de YouTube
        channel: Nombre del canal (opcional)

    Returns:
        True si parece ser video oficial, False si es lyric/cover/etc.
    """
    title_lower = video_title.lower()

    # Check for bad keywords in title
    for keyword in _BAD_VIDEO_KEYWORDS:
        if keyword in title_lower:
            return False

    # Check channel if provided (canales de usuarios suelen tener patrones)
    if channel:
        channel_lower = channel.lower()
        # Canales como "VEVO" o del artista son buenos
        if "vevo" in channel_lower:
            return True
        # Canales con números al final son通常是 de usuario
        if any(c.isdigit() for c in channel.split()[-1:]):
            return False

    # Si no tiene keywords bad, assumimos oficial
    return True


def is_preferred_video(video_title: str, channel: str = "") -> bool:
    """Check if video is preferred (official audio, live performance)."""
    title_lower = video_title.lower()
    for keyword in _GOOD_VIDEO_KEYWORDS:
        if keyword in title_lower:
            return True
    return False


def is_bad_video(video_title: str, channel: str = "") -> bool:
    """Check if video should be rejected (lyric, cover, remix, etc.)."""
    title_lower = video_title.lower()
    for keyword in _BAD_VIDEO_KEYWORDS:
        if keyword in title_lower:
            return True
    return False


def should_ask_user(video_title: str, channel: str = "") -> bool:
    """Check if video is ambiguous - ask user to decide ('live', etc.)."""
    title_lower = video_title.lower()
    for keyword in _AMBIGUOUS_VIDEO_KEYWORDS:
        if keyword in title_lower:
            return True
    return False


def classify_video(video_title: str, channel: str = "") -> str:
    """Classify video quality: 'preferred', 'bad', 'ask_user', or 'neutral'."""
    if is_preferred_video(video_title, channel):
        return "preferred"
    if is_bad_video(video_title, channel):
        return "bad"
    if should_ask_user(video_title, channel):
        return "ask_user"
    return "neutral"


# Estrategias en el mismo orden que dl-music-system.sh
_FORMAT_STRATEGIES = [
    # 1. Android client (evita 403 SABR)
    ["--extractor-args", "youtube:player_client=android"],
    # 2. Estándar (sin args extra)
    [],
    # 3. m4a/best para SABR
    ["--format", "bestaudio[ext=m4a]/bestaudio/best"],
    # 4. bestaudio
    ["--format", "bestaudio"],
    # 5. Android + bestaudio
    ["--extractor-args", "youtube:player_client=android", "--format", "bestaudio"],
    # 6. SABR workaround
    ["--extractor-args", "youtube:formats=missing_pot"],
    # 7. SABR workaround + best (último recurso)
    ["--extractor-args", "youtube:formats=missing_pot", "--format", "best"],
]


def _fetch_thumbnail(thumbnail_url: str, display_id: str) -> Optional[str]:
    """Descarga el thumbnail a /tmp; retorna la ruta o None si falla o URL vacía."""
    if not thumbnail_url:
        return None
    tmp = f"/tmp/thumbnail_{display_id}.jpg"
    try:
        result = subprocess.run(
            ["curl", "-sL", thumbnail_url, "-o", tmp],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0 and os.path.exists(tmp):
            # Verificar que es imagen (heurística: tamaño > 1KB)
            if os.path.getsize(tmp) > 1024:
                return tmp
    except Exception as e:
        logger.debug("thumbnail fetch error: %s", e)
    if os.path.exists(tmp):
        os.unlink(tmp)
    return None


class YtDlpDownloader:
    """
    Descarga un track como MP3 usando yt-dlp y embebe metadatos.
    Compatible con cualquier fuente que yt-dlp soporte (YouTube, SoundCloud, etc.).
    Requiere yt-dlp y ffmpeg en PATH.
    """

    def __init__(self, lib_base_dir: str, ytdlp_bin: str = "yt-dlp"):
        self.lib_base_dir = lib_base_dir
        self.ytdlp_bin = ytdlp_bin
        self.bin = ytdlp_bin
        self._tagger = MetadataTagger()

    def check_tools(self) -> Optional[DownloadError]:
        if not shutil.which(self.ytdlp_bin):
            return DownloadError.EXTERNAL_TOOL
        return None

    def download(
        self,
        track_ref: TrackRef,
        artist: str,
        title: str,
        genre_slug: str,
    ) -> tuple[DownloadStatus, str, Optional[DownloadError], str]:
        """
        Retorna (status, filepath, error, error_detail).
        Acepta cualquier plataforma via TrackRef.url.
        """
        genre_subdir = GENRE_DIR.get(genre_slug)
        if genre_subdir is None:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.INVALID_GENRE,
                f"slug desconocido: {genre_slug}",
            )

        dest_dir = os.path.join(self.lib_base_dir, genre_subdir)
        os.makedirs(dest_dir, exist_ok=True)

        # SSOT: canonical_filename (sanitize_filename_component aplicado)
        filename = canonical_filename(artist, title, ".mp3")
        filepath = os.path.join(dest_dir, filename)

        # Intentar cada estrategia de formato
        success = False
        for i, extra_args in enumerate(_FORMAT_STRATEGIES, 1):
            cmd = (
                [self.ytdlp_bin]
                + _YTDLP_BASE
                + extra_args
                + ["-o", filepath, track_ref.url]
            )
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0 and os.path.exists(filepath):
                    logger.debug(
                        "downloader: estrategia %d exitosa para %s",
                        i,
                        track_ref.display_id,
                    )
                    success = True
                    break
            except subprocess.TimeoutExpired:
                logger.debug("downloader: estrategia %d timeout", i)
            except Exception as e:
                logger.debug("downloader: estrategia %d excepción: %s", i, e)

        if not success:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.DOWNLOAD_FAILED,
                "todas las estrategias fallaron",
            )

        # Thumbnail y metadatos
        thumbnail = _fetch_thumbnail(track_ref.thumbnail_url, track_ref.display_id)
        # Pasar artist/title sanitizados al tagger para consistencia BD/tag/filename
        tagged = self._tagger.tag(
            filepath,
            sanitize_filename_component(artist),
            sanitize_filename_component(title),
            genre_subdir,
            thumbnail,
        )
        if thumbnail and os.path.exists(thumbnail):
            os.unlink(thumbnail)

        if not tagged:
            logger.warning(
                "downloader: tagging falló para %s - %s (archivo OK)", artist, title
            )
            # No es error bloqueante: el archivo descargado igual vale

        return DownloadStatus.DOWNLOADED, filepath, None, ""

    def download_with_video(
        self,
        track_ref: TrackRef,
        artist: str,
        title: str,
        genre_slug: str,
    ) -> tuple[DownloadStatus, str, Optional[DownloadError], str]:
        """
        Descarga video + audio como MP4.
        Usa formato 'bestvideo+bestaudio' para mejor calidad.
        Retorna (status, filepath, error, error_detail).
        """
        genre_subdir = GENRE_DIR.get(genre_slug)
        if genre_subdir is None:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.INVALID_GENRE,
                f"slug desconocido: {genre_slug}",
            )

        dest_dir = os.path.join(self.lib_base_dir, genre_subdir)
        os.makedirs(dest_dir, exist_ok=True)

        filename = f"{sanitize_filename(artist)} - {sanitize_filename(title)}.mp4"
        filepath = os.path.join(dest_dir, filename)

        # Formato: H.264 (avc1) video + AAC (m4a) audio para compatibilidad
        # completa con QuickTime / Finder preview / Photos app / iOS.
        # Fallback: intenta con filtros más relajados si H.264 no está disponible.
        format_strategies = [
            # Preferido: H.264 video + AAC audio, container MP4
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/best[vcodec^=avc1][ext=mp4]",
            # Fallback 1: H.264 en cualquier container
            "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]",
            # Fallback 2: mejor MP4 disponible
            "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]",
            # Último recurso: lo que haya (puede ser VP9/Opus)
            "bestvideo+bestaudio/best",
        ]

        result = None
        for fmt in format_strategies:
            cmd = [
                self.ytdlp_bin,
                "-f", fmt,
                "--merge-output-format", "mp4",
                "-o", filepath,
                track_ref.url,
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0 and os.path.exists(filepath):
                    logger.debug(
                        "downloader: video %s descargado con fmt=%s",
                        track_ref.display_id, fmt,
                    )
                    # Escribir tags MP4 (©ART, ©nam, ©alb=genre_slug, ©gen) + covr
                    self._tag_mp4(filepath, artist, title, genre_subdir, track_ref)
                    return DownloadStatus.DOWNLOADED, filepath, None, ""
                # Si falló por "Requested format not available", probar siguiente estrategia
                if "Requested format is not available" in (result.stderr or ""):
                    logger.debug("downloader: fmt %s no disponible, probando siguiente", fmt)
                    continue
                # Error distinto → abortar
                break
            except subprocess.TimeoutExpired:
                return (
                    DownloadStatus.DOWNLOAD_ERROR,
                    "",
                    DownloadError.DOWNLOAD_FAILED,
                    "video download timeout (300s)",
                )

        # Si llegamos acá, todas las estrategias fallaron
        return (
            DownloadStatus.DOWNLOAD_ERROR,
            "",
            DownloadError.DOWNLOAD_FAILED,
            (result.stderr if result else "video download failed"),
        )

    def _tag_mp4(
        self,
        filepath: str,
        artist: str,
        title: str,
        genre_slug: str,
        track_ref: "TrackRef",
    ) -> None:
        """Escribe tags QuickTime (©ART, ©nam, ©alb=real album, ©gen=nombre género)
        + covr en MP4. No bloquea si falla."""
        try:
            from mpc.curator.fixers._mp4_utils import write_mp4_tags
            from mpc.utils.text import sanitize_filename_component as _san
            from mpc.catalog.genres import genre_name as _gname

            # Resolver álbum real
            album = ""
            try:
                from mpc.curator.album_resolver import build_default_resolver
                r = build_default_resolver().resolve(artist, title)
                album = r.get("album", "")
            except Exception:
                pass

            write_mp4_tags(
                filepath,
                artist=_san(artist),
                title=_san(title),
                album=album or None,
                genre=_gname(genre_slug) or None,
                overwrite=True,
            )
        except Exception as e:
            logger.warning("downloader: tag_mp4 falló para %s: %s",
                           track_ref.display_id, e)

        # Intentar también embeber covr desde thumbnail YouTube
        try:
            from mpc.curator.fixers.thumbnails import fetch_from_youtube
            from mutagen.mp4 import MP4, MP4Cover
            jpg = fetch_from_youtube(track_ref.display_id)
            if jpg:
                mp4 = MP4(filepath)
                mp4["covr"] = [MP4Cover(jpg, imageformat=MP4Cover.FORMAT_JPEG)]
                mp4.save()
        except Exception as e:
            logger.debug("downloader: covr embed falló para %s: %s",
                         track_ref.display_id, e)


class SpotdlDownloader:
    """
    Descarga un track de Spotify como MP3 usando spotdl.
    Solo se invoca cuando track_ref.platform == SPOTIFY.
    Requiere spotdl en PATH (pip install spotdl).
    """

    def __init__(self, lib_base_dir: str, spotdl_bin: str = "spotdl"):
        self.lib_base_dir = lib_base_dir
        self.spotdl_bin = spotdl_bin
        self.bin = spotdl_bin
        self._tagger = MetadataTagger()

    def check_tools(self) -> Optional[DownloadError]:
        if not shutil.which(self.spotdl_bin):
            return DownloadError.EXTERNAL_TOOL
        return None

    def download(
        self,
        track_ref: TrackRef,
        artist: str,
        title: str,
        genre_slug: str,
    ) -> tuple:
        """Retorna (status, filepath, error, error_detail)."""
        genre_subdir = GENRE_DIR.get(genre_slug)
        if genre_subdir is None:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.INVALID_GENRE,
                f"slug desconocido: {genre_slug}",
            )

        dest_dir = os.path.join(self.lib_base_dir, genre_subdir)
        os.makedirs(dest_dir, exist_ok=True)

        # spotdl usará los metadatos de Spotify para nombrar el archivo
        # Template: "{artist} - {title}.{ext}" para consistencia con la librería
        output_template = os.path.join(dest_dir, "{artist} - {title}.{ext}")

        # Snapshot de archivos antes para detectar el nuevo
        before = set(os.listdir(dest_dir))

        cmd = [
            self.spotdl_bin,
            "--audio-quality",
            "320k",
            "--embed-metadata",
            "--output",
            output_template,
            track_ref.url,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.DOWNLOAD_FAILED,
                "spotdl timeout (300s)",
            )
        except Exception as e:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.DOWNLOAD_FAILED,
                str(e),
            )

        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-400:]
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.DOWNLOAD_FAILED,
                f"spotdl exit {result.returncode}: {tail}",
            )

        # Encontrar el archivo nuevo en dest_dir
        after = set(os.listdir(dest_dir))
        new_files = [f for f in (after - before) if f.lower().endswith(".mp3")]

        if not new_files:
            return (
                DownloadStatus.DOWNLOAD_ERROR,
                "",
                DownloadError.DOWNLOAD_FAILED,
                "archivo no encontrado tras spotdl",
            )

        filepath = os.path.join(dest_dir, new_files[0])

        # Tagging adicional con nuestros metadatos (artista/título del CSV)
        thumbnail = _fetch_thumbnail(track_ref.thumbnail_url, track_ref.display_id)
        # Pasar artist/title sanitizados al tagger para consistencia BD/tag/filename
        tagged = self._tagger.tag(
            filepath,
            sanitize_filename_component(artist),
            sanitize_filename_component(title),
            genre_subdir,
            thumbnail,
        )
        if thumbnail and os.path.exists(thumbnail):
            os.unlink(thumbnail)
        if not tagged:
            logger.warning(
                "spotdl: tagging falló para %s - %s (archivo OK)", artist, title
            )

        return DownloadStatus.DOWNLOADED, filepath, None, ""


class DownloaderStep(BaseStep):
    """
    Step que despacha al downloader correcto según track_ref.platform:
      - SPOTIFY  → SpotdlDownloader
      - resto    → YtDlpDownloader (YouTube, SoundCloud, URL directa)

    Requiere en ctx: track_ref (TrackRef), genre_slug (normalizado), request.
    Setea en ctx: filepath, download_status, error, error_detail.
    """

    def __init__(self, ytdlp: YtDlpDownloader, spotdl: SpotdlDownloader):
        self._ytdlp = ytdlp
        self._spotdl = spotdl

    def run(self, ctx: Dict[str, Any]) -> None:
        if ctx.get("skip"):
            return

        req = ctx["request"]
        if req.dry_run:
            ctx["status_override"] = DownloadStatus.DRY_RUN
            return

        track_ref: Optional[TrackRef] = ctx.get("track_ref")
        if not track_ref:
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.DOWNLOAD_ERROR
            ctx["error"] = DownloadError.SEARCH_NO_CANDIDATE
            ctx["error_detail"] = "track_ref no disponible en contexto"
            return

        dl = self._spotdl if track_ref.platform == SPOTIFY else self._ytdlp

        tool_err = dl.check_tools()
        if tool_err:
            ctx["skip"] = True
            ctx["skip_status"] = DownloadStatus.DOWNLOAD_ERROR
            ctx["error"] = tool_err
            ctx["error_detail"] = f"{dl.bin} no encontrado en PATH"
            return

        genre_slug = ctx.get("genre_slug", "")
        artist = ctx.get("display_artist", req.artist)
        title = ctx.get("display_title", req.title)

        status, filepath, error, detail = dl.download(
            track_ref, artist, title, genre_slug
        )
        ctx["filepath"] = filepath
        ctx["download_status"] = status
        if error:
            ctx["error"] = error
            ctx["error_detail"] = detail
