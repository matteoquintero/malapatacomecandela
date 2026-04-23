# mpc/curator/fixers/thumbnails.py
# -*- coding: utf-8 -*-
"""
ThumbnailFixer: baja e inyecta carátulas APIC en MP3s.

Cadena de fuentes (en orden):
  1. MusicBrainz Cover Art Archive (si hay mbid) — carátula oficial del álbum
  2. YouTube del audio_source_id — carátula del audio oficial
  3. YouTube del video_source_id — último recurso (puede ser concert)

Solo aplica a MP3 (ID3 APIC). Los MP4 tienen su propio fixer:
`curator fix-video-thumbnails` que usa el atom `covr`.

No re-descarga el MP3, solo añade el frame APIC con mutagen.
"""

from __future__ import annotations

import os
import urllib.request
from typing import Optional, Tuple

from mpc.library.repository import TrackRepository

try:
    from mutagen.id3 import ID3, APIC, ID3NoHeaderError
except ImportError:
    ID3 = None

YT_TEMPLATES = [
    "https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
]

CAA_TEMPLATES = [
    "https://coverartarchive.org/release/{mbid}/front-500",
    "https://coverartarchive.org/release/{mbid}/front-250",
    "https://coverartarchive.org/release/{mbid}/front",
]


def _http_get_bytes(url: str, timeout: int = 15) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mala-pata-curator/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = resp.read()
                if len(data) > 2048:
                    return data
    except Exception:
        pass
    return None


def fetch_from_caa(mbid: str) -> Optional[bytes]:
    """Cover Art Archive por MusicBrainz release ID."""
    for tpl in CAA_TEMPLATES:
        data = _http_get_bytes(tpl.format(mbid=mbid))
        if data:
            return data
    return None


def fetch_from_youtube(video_id: str) -> Optional[bytes]:
    """Thumbnail de YouTube (maxres → hq → mq)."""
    for tpl in YT_TEMPLATES:
        data = _http_get_bytes(tpl.format(vid=video_id))
        if data:
            return data
    return None


def embed_thumbnail(mp3_path: str, jpg_data: bytes) -> None:
    """Embebe un JPG como APIC (front cover) en el MP3."""
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=jpg_data))
    tags.save(mp3_path, v2_version=3)


class ThumbnailFixer:
    """Procesa todos los tracks con archivo + sin thumbnail."""

    def __init__(self, repo: TrackRepository):
        self.repo = repo

    def run(self, dry_run: bool = False, limit: Optional[int] = None) -> dict:
        tracks = self.repo.without_thumbnail_with_any_source()
        if limit:
            tracks = tracks[:limit]

        from mpc.curator.status import CuratorStatus

        fixed = 0
        failed = 0
        by_source = {"caa": 0, "audio": 0, "video": 0}

        for i, t in enumerate(tracks, 1):
            label = f"[{i}/{len(tracks)}] {t['artist']} - {t['title']}"
            filepath = t.get("filepath") or ""

            if not filepath or not os.path.isfile(filepath):
                print(f"{label} ⚠️  sin filepath válido")
                failed += 1
                continue

            data, source = self._fetch_any(t)
            if not data:
                print(f"{label} ❌ ninguna fuente dio thumbnail")
                failed += 1
                continue

            if dry_run:
                print(f"{label} [DRY-RUN] fuente={source}, {len(data)} bytes")
                by_source[source] += 1
                continue

            try:
                embed_thumbnail(filepath, data)
            except Exception as e:
                print(f"{label} ❌ error embebiendo: {e}")
                failed += 1
                continue

            warning = "  ⚠️ visual/concert" if source == "video" else ""
            print(f"{label} ✅ fuente={source} ({len(data)} bytes){warning}")
            by_source[source] += 1
            fixed += 1

            # recompute status
            new_status = CuratorStatus.OK
            if not t.get("has_valid_tags"):
                new_status = CuratorStatus.NEEDS_TAGS
            if not t.get("filename_ok"):
                new_status = CuratorStatus.NEEDS_RENAME
            if not t.get("genre_folder_ok") and t.get("genre_slug"):
                new_status = CuratorStatus.NEEDS_MOVE

            self.repo.update_curator_flags(
                t["track_id"],
                has_thumbnail=1,
                curator_status=new_status,
            )

        return {
            "total": len(tracks),
            "fixed": fixed,
            "failed": failed,
            "by_source": by_source,
        }

    def _fetch_any(self, track: dict) -> Tuple[Optional[bytes], Optional[str]]:
        """Intenta CAA → audio → video. Devuelve (bytes, source_label)."""
        mbid = (track.get("mbid") or "").strip()
        audio_id = (track.get("audio_source_id") or "").strip()
        video_id = (track.get("video_source_id") or "").strip()

        if mbid:
            data = fetch_from_caa(mbid)
            if data:
                return data, "caa"
        if audio_id:
            data = fetch_from_youtube(audio_id)
            if data:
                return data, "audio"
        if video_id:
            data = fetch_from_youtube(video_id)
            if data:
                return data, "video"
        return None, None
