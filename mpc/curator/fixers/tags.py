# mpc/curator/fixers/tags.py
# -*- coding: utf-8 -*-
"""
TagFixer: completa tags ID3 faltantes leyendo BD + MusicBrainz.
Solo rellena tags vacíos — no sobrescribe.
"""

from __future__ import annotations

import os
from typing import Optional

from mpc.curator.status import CuratorStatus
from mpc.library.repository import TrackRepository

try:
    from mutagen.id3 import ID3, TPE1, TIT2, TALB, TCON, TDRC, ID3NoHeaderError
except ImportError:
    ID3 = None


def _ensure_tag(tags, frame_cls, text: str) -> bool:
    """Agrega un frame si no existe o está vacío. Devuelve True si cambió."""
    existing = tags.get(frame_cls.__name__)
    current = str(existing) if existing else ""
    if not current.strip() and text.strip():
        tags.add(frame_cls(encoding=3, text=text))
        return True
    return False


def _mb_lookup(artist: str, title: str) -> dict:
    """Busca album + year en MusicBrainz. Vacío si falla."""
    try:
        from mpc.sources.musicbrainz import mb_get, _lucene_escape

        q = f'artist:"{_lucene_escape(artist)}" AND recording:"{_lucene_escape(title)}"'
        data = mb_get("recording", {"query": q, "limit": 5})
        recs = data.get("recordings", [])
        if not recs:
            return {}
        rec = recs[0]
        releases = rec.get("releases", [])
        album = releases[0]["title"] if releases else ""
        year = ""
        if releases:
            date = releases[0].get("date", "")
            year = date.split("-")[0] if date else ""
        return {"album": album, "year": year}
    except Exception:
        return {}


class TagFixer:
    def __init__(self, repo: TrackRepository):
        self.repo = repo

    def run(self, dry_run: bool = False, limit: Optional[int] = None,
            use_mb: bool = True) -> dict:
        """Llena tags faltantes. TALB usa AlbumResolver (MB/Discogs/LLM).
        TCON = nombre legible del género (desde GENRE_DB)."""
        from mpc.curator.album_resolver import build_default_resolver
        from mpc.catalog.genres import genre_name as _genre_name
        resolver = build_default_resolver() if use_mb else None

        tracks = self.repo.without_valid_tags()
        if limit:
            tracks = tracks[:limit]

        fixed = 0
        failed = 0

        for i, t in enumerate(tracks, 1):
            artist = t["artist"]
            title = t["title"]
            filepath = t.get("filepath") or ""
            label = f"[{i}/{len(tracks)}] {artist} - {title}"

            if not filepath or not os.path.isfile(filepath):
                print(f"{label} ⚠️  sin filepath válido")
                failed += 1
                continue

            genre_slug = t.get("genre_slug") or ""
            tcon_name = _genre_name(genre_slug)
            album = t.get("album") or ""
            year = t.get("year") or ""

            # Resolver álbum si está vacío
            if not album and resolver:
                r = resolver.resolve(artist, title, mbid=t.get("mbid") or "")
                album = r.get("album", "")
                if not year:
                    year = r.get("year", "")

            if dry_run:
                print(f"{label} [DRY-RUN] TALB={album!r} TCON={tcon_name!r} TDRC={year!r}")
                continue

            try:
                try:
                    tags = ID3(filepath)
                except ID3NoHeaderError:
                    tags = ID3()

                changed = False
                changed |= _ensure_tag(tags, TPE1, artist)
                changed |= _ensure_tag(tags, TIT2, title)
                if album:
                    changed |= _ensure_tag(tags, TALB, album)
                if tcon_name:
                    changed |= _ensure_tag(tags, TCON, tcon_name)
                if year:
                    changed |= _ensure_tag(tags, TDRC, year)

                if changed:
                    tags.save(filepath, v2_version=3)

                # Recalcular has_valid_tags
                final_artist = str(tags.get("TPE1", "") or "").strip()
                final_title = str(tags.get("TIT2", "") or "").strip()
                final_album = str(tags.get("TALB", "") or "").strip()
                valid = bool(final_artist and final_title and final_album)

                # Llenar también tags MP4 vacíos si hay video_filepath
                bd_video = t.get("video_filepath") or ""
                if bd_video and os.path.isfile(bd_video):
                    try:
                        from mpc.curator.fixers._mp4_utils import write_mp4_tags
                        write_mp4_tags(
                            bd_video,
                            artist=artist, title=title,
                            album=album or None, genre=tcon_name or None,
                            year=year or None,
                            overwrite=False,
                        )
                    except Exception as e:
                        print(f"{label} ⚠️ video tags error: {e}")

                # Decidir nuevo curator_status
                has_thumb = bool(t.get("has_thumbnail"))
                if valid and has_thumb:
                    new_status = CuratorStatus.OK
                elif not has_thumb:
                    new_status = CuratorStatus.NEEDS_THUMBNAIL
                else:
                    new_status = CuratorStatus.OK

                self.repo.update_curator_flags(
                    t["track_id"],
                    has_valid_tags=int(valid),
                    album=album,
                    year=year,
                    curator_status=new_status,
                )
                print(f"{label} ✅ tags (album={album!r}, source=...)")
                fixed += 1
            except Exception as e:
                print(f"{label} ❌ error: {e}")
                failed += 1

        return {"total": len(tracks), "fixed": fixed, "failed": failed}
