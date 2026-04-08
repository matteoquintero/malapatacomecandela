# mpc/download/steps/tagger.py
# -*- coding: utf-8 -*-
"""
MetadataTagger: embebe metadatos ID3 y artwork en el MP3 descargado.

Reemplaza la sección ffmpeg de dl-music-system.sh con Python puro.
Si ffmpeg falla, el archivo queda sin metadatos pero el flujo continúa
(no es un error bloqueante).
"""

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger("mpc.acquisition.steps.tagger")

_FFMPEG_QUIET = ["-y", "-v", "quiet"]


class MetadataTagger:
    """
    Embebe title, artist, album (genre dir), genre y artwork en un MP3
    usando ffmpeg. Opera sobre el archivo in-place via un fichero temporal.
    """

    def tag(
        self,
        filepath: str,
        artist: str,
        title: str,
        genre_dir: str,
        thumbnail_path: Optional[str] = None,
    ) -> bool:
        """
        Retorna True si los metadatos se aplicaron correctamente.
        Retorna False si ffmpeg no está disponible o falla (no lanza excepción).
        """
        if not shutil.which("ffmpeg"):
            logger.warning("tagger: ffmpeg no encontrado en PATH, sin metadatos")
            return False

        genre_label = genre_dir.replace("_", " ")
        year = str(__import__("datetime").datetime.now().year)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            if thumbnail_path and os.path.exists(thumbnail_path):
                ok = self._tag_with_artwork(
                    filepath, tmp_path, artist, title, genre_dir, genre_label, year, thumbnail_path
                )
                if not ok:
                    logger.debug("tagger: artwork falló, reintentando sin él")
                    ok = self._tag_without_artwork(
                        filepath, tmp_path, artist, title, genre_dir, genre_label, year
                    )
            else:
                ok = self._tag_without_artwork(
                    filepath, tmp_path, artist, title, genre_dir, genre_label, year
                )

            if ok and os.path.exists(tmp_path):
                shutil.move(tmp_path, filepath)
                return True
            return False

        except Exception as e:
            logger.warning("tagger: excepción inesperada: %s", e)
            return False
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _tag_with_artwork(
        self, src: str, dst: str, artist: str, title: str,
        genre_dir: str, genre_label: str, year: str, thumb: str
    ) -> bool:
        cmd = [
            "ffmpeg",
            "-i", src,
            "-i", thumb,
            "-map", "0:a",
            "-map", "1:v",
            "-c:a", "copy",
            "-c:v", "mjpeg",
            "-disposition:v", "attached_pic",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            "-metadata", f"album={genre_dir}",
            "-metadata", f"genre={genre_label}",
            "-metadata", f"date={year}",
            dst,
            *_FFMPEG_QUIET,
        ]
        return subprocess.run(cmd, capture_output=True).returncode == 0

    def _tag_without_artwork(
        self, src: str, dst: str, artist: str, title: str,
        genre_dir: str, genre_label: str, year: str
    ) -> bool:
        cmd = [
            "ffmpeg",
            "-i", src,
            "-c:a", "copy",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            "-metadata", f"album={genre_dir}",
            "-metadata", f"genre={genre_label}",
            "-metadata", f"date={year}",
            dst,
            *_FFMPEG_QUIET,
        ]
        return subprocess.run(cmd, capture_output=True).returncode == 0
