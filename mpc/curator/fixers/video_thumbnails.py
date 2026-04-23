# mpc/curator/fixers/video_thumbnails.py
# -*- coding: utf-8 -*-
"""
VideoThumbnailFixer: embebe el thumbnail de YouTube (por video_source_id)
como atom 'covr' en los archivos MP4.

Diferente a ThumbnailFixer (MP3 → APIC desde CAA): para videos usamos
directamente la imagen oficial del video en YouTube.
"""

from __future__ import annotations

import os
import urllib.request
from typing import Optional

from mpc.library.repository import TrackRepository

try:
    from mutagen.mp4 import MP4, MP4Cover
except ImportError:
    MP4 = None
    MP4Cover = None

YT_TEMPLATES = [
    "https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
]


def _fetch_youtube_thumbnail(video_id: str) -> Optional[bytes]:
    for tpl in YT_TEMPLATES:
        url = tpl.format(vid=video_id)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mala-pata/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 2048:
                        return data
        except Exception:
            continue
    return None


def _embed_covr(mp4_path: str, jpg_data: bytes) -> None:
    mp4 = MP4(mp4_path)
    mp4["covr"] = [MP4Cover(jpg_data, imageformat=MP4Cover.FORMAT_JPEG)]
    mp4.save()


class VideoThumbnailFixer:
    """Procesa tracks con MP4 + video_source_id pero sin covr atom."""

    def __init__(self, repo: TrackRepository):
        self.repo = repo

    def run(self, dry_run: bool = False, limit: Optional[int] = None) -> dict:
        if MP4 is None:
            print("❌ mutagen.mp4 no disponible")
            return {"total": 0}

        tracks = self.repo.without_video_thumbnail_with_video()
        if limit:
            tracks = tracks[:limit]

        stats = {"total": len(tracks), "fixed": 0, "failed": 0, "skipped": 0}

        for i, t in enumerate(tracks, 1):
            artist = t["artist"]
            title = t["title"]
            video_fp = t.get("video_filepath") or ""
            video_id = t.get("video_source_id") or ""
            label = f"[{i}/{len(tracks)}] {artist} - {title}"

            if not video_fp or not os.path.isfile(video_fp):
                print(f"{label} ⚠️  MP4 inexistente")
                stats["skipped"] += 1
                continue

            if not video_id:
                print(f"{label} ⚠️  sin video_source_id")
                stats["skipped"] += 1
                continue

            if dry_run:
                print(f"{label} [DRY-RUN] bajaría covr de {video_id}")
                continue

            data = _fetch_youtube_thumbnail(video_id)
            if not data:
                print(f"{label} ❌ no se pudo bajar thumbnail YT")
                stats["failed"] += 1
                continue

            try:
                _embed_covr(video_fp, data)
            except Exception as e:
                print(f"{label} ❌ embebiendo covr: {e}")
                stats["failed"] += 1
                continue

            self.repo.update_curator_flags(
                t["track_id"], has_video_thumbnail=1,
            )
            print(f"{label} ✅ covr embebido ({len(data)} bytes)")
            stats["fixed"] += 1

        return stats
