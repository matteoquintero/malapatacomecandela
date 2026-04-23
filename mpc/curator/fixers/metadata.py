# mpc/curator/fixers/metadata.py
# -*- coding: utf-8 -*-
"""
MetadataFixer: sincroniza BD.artist/title + filename + tags ID3/MP4.

Regla de diseño enforzada:
  - BD.artist / BD.title sanitizados (sanitize_filename_component)
  - Filename = canonical_filename(BD.artist, BD.title, ext)
  - Tag TPE1/©ART == BD.artist
  - Tag TIT2/©nam == BD.title
  - Tag TALB/©alb == BD.genre_slug (invariante activa)

Transaccional: rename → tags → BD. Si falla tags, revierte rename.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from mpc.curator.status import CuratorStatus
from mpc.library.repository import TrackRepository
from mpc.utils.text import sanitize_filename_component, canonical_filename
from mpc.curator.fixers._file_ops import rename_with_2step_fallback
from mpc.curator.fixers._mp4_utils import write_mp4_tags
from mpc.curator.album_resolver import build_default_resolver
from mpc.catalog.genres import genre_name as _genre_name

try:
    from mutagen.id3 import ID3, TPE1, TIT2, TALB, TCON, ID3NoHeaderError
    from mutagen.mp4 import MP4
except ImportError:
    ID3 = None
    MP4 = None


class MetadataFixer:
    def __init__(self, repo: TrackRepository, resolver=None):
        self.repo = repo
        self._resolver = resolver  # lazy-build if None

    def _get_resolver(self):
        if self._resolver is None:
            self._resolver = build_default_resolver()
        return self._resolver

    def run(self, dry_run: bool = True, limit: Optional[int] = None) -> dict:
        if ID3 is None:
            print("❌ mutagen no disponible")
            return {"total": 0}

        tracks = self.repo.without_consistent_metadata()
        if limit:
            tracks = tracks[:limit]

        stats = {
            "total": len(tracks),
            "bd_updated": 0,
            "renamed": 0,
            "tags_written": 0,
            "album_resolved": 0,
            "by_source": {"mb_mbid": 0, "mb_search": 0, "discogs": 0, "llm": 0, "none": 0},
            "failed": 0,
            "skipped": 0,
            "unchanged": 0,
        }

        for i, t in enumerate(tracks, 1):
            fp = t.get("filepath") or ""
            if not fp or not os.path.isfile(fp):
                print(f"[{i}/{len(tracks)}] {t['artist']} - {t['title']} ⚠️ archivo inexistente")
                stats["skipped"] += 1
                continue

            raw_artist = t["artist"]
            raw_title = t["title"]
            genre_slug = t.get("genre_slug") or ""
            tcon_name = _genre_name(genre_slug)

            new_artist = sanitize_filename_component(raw_artist)
            new_title = sanitize_filename_component(raw_title)

            # Resolver álbum real (MB → Discogs → LLM → vacío)
            current_album = t.get("album") or ""
            resolved_album = current_album
            resolved_year = t.get("year") or ""
            if not current_album:
                r = self._get_resolver().resolve(
                    raw_artist, raw_title, mbid=t.get("mbid") or ""
                )
                resolved_album = r.get("album", "")
                resolved_year = r.get("year", "") or resolved_year
                stats["by_source"][r.get("source", "none")] = stats["by_source"].get(r.get("source", "none"), 0) + 1
                if resolved_album:
                    stats["album_resolved"] += 1

            current = Path(fp)
            ext = current.suffix
            target_name = canonical_filename(raw_artist, raw_title, ext)
            target_path = current.parent / target_name

            print(f"[{i}/{len(tracks)}] {raw_artist} - {raw_title}")
            changes = []
            if raw_artist != new_artist:
                changes.append(f"  BD.artist: {raw_artist!r} → {new_artist!r}")
            if raw_title != new_title:
                changes.append(f"  BD.title:  {raw_title!r} → {new_title!r}")
            if current.name != target_name:
                changes.append(f"  filename:  {current.name!r} → {target_name!r}")
            changes.append(
                f"  tags:      TPE1={new_artist!r} TIT2={new_title!r} TALB={resolved_album!r} TCON={tcon_name!r}"
            )
            for c in changes:
                print(c)

            if dry_run:
                print(f"  [DRY-RUN]")
                continue

            # 1. Update BD artist/title si cambiaron
            bd_changed = False
            if raw_artist != new_artist or raw_title != new_title:
                try:
                    self.repo.update_curator_flags(
                        t["track_id"],
                        artist=new_artist,
                        title=new_title,
                    )
                    bd_changed = True
                    stats["bd_updated"] += 1
                except Exception as e:
                    print(f"  ❌ BD update: {e}")
                    stats["failed"] += 1
                    continue

            new_fp = str(current)

            # 2. Rename archivo si necesario (helper maneja APFS case-insensitive)
            if current.name != target_name:
                ok, new_path, err = rename_with_2step_fallback(current, target_path)
                if not ok:
                    print(f"  ❌ {err}")
                    stats["failed"] += 1
                    continue
                if new_path != current:
                    new_fp = str(new_path)
                    stats["renamed"] += 1

            # 3. Escribir tags (transaccional)
            try:
                if ext.lower() == ".mp3":
                    self._write_id3(new_fp, new_artist, new_title, genre_slug,
                                     album=resolved_album, year=resolved_year)
                elif ext.lower() in (".mp4", ".m4a"):
                    self._write_mp4(new_fp, new_artist, new_title, genre_slug,
                                     album=resolved_album, year=resolved_year)
                stats["tags_written"] += 1
            except Exception as e:
                print(f"  ❌ tags: {e}")
                # Revertir rename si se aplicó
                if new_fp != str(current) and os.path.isfile(new_fp):
                    try:
                        os.rename(new_fp, str(current))
                        stats["renamed"] -= 1
                        new_fp = str(current)
                    except OSError:
                        pass
                stats["failed"] += 1
                continue

            # 3b. Sincronizar MP4 asociado si existe
            bd_video_fp = t.get("video_filepath") or ""
            if bd_video_fp and os.path.isfile(bd_video_fp):
                video_current = Path(bd_video_fp)
                video_target_name = canonical_filename(
                    raw_artist, raw_title, video_current.suffix
                )
                video_target = video_current.parent / video_target_name
                new_video_fp = str(video_current)
                if video_current.name != video_target_name:
                    ok, new_video_path, err = rename_with_2step_fallback(
                        video_current, video_target
                    )
                    if ok and new_video_path != video_current:
                        new_video_fp = str(new_video_path)
                        stats["video_renamed"] = stats.get("video_renamed", 0) + 1
                    elif not ok:
                        print(f"  ⚠️ video rename: {err}")
                try:
                    if write_mp4_tags(
                        new_video_fp,
                        artist=new_artist, title=new_title,
                        album=resolved_album or None,
                        genre=tcon_name or None,
                        year=resolved_year or None,
                        overwrite=True,
                    ):
                        stats["video_tags_written"] = stats.get("video_tags_written", 0) + 1
                except Exception as e:
                    print(f"  ⚠️ video tags: {e}")
                if new_video_fp != bd_video_fp:
                    self.repo.update_curator_flags(
                        t["track_id"], video_filepath=new_video_fp
                    )

            # 4. Update BD flags finales (audio)
            has_thumb = bool(t.get("has_thumbnail"))
            if has_thumb:
                new_status = CuratorStatus.OK
            else:
                new_status = CuratorStatus.NEEDS_THUMBNAIL

            update_kwargs = {
                "metadata_consistent": 1,
                "has_valid_tags": 1,
                "filename_ok": 1,
                "curator_status": new_status,
            }
            if new_fp != fp:
                update_kwargs["filepath"] = new_fp
            if resolved_album:
                update_kwargs["album"] = resolved_album
            if resolved_year:
                update_kwargs["year"] = resolved_year
            self.repo.update_curator_flags(t["track_id"], **update_kwargs)
            print(f"  ✅ sync")

        return stats

    def _write_id3(self, path: str, artist: str, title: str, genre_slug: str,
                    album: str = "", year: str = "") -> None:
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall("TPE1")
        tags.add(TPE1(encoding=3, text=artist))
        tags.delall("TIT2")
        tags.add(TIT2(encoding=3, text=title))
        # TALB: album real (resolved), NO genre_slug
        if album:
            tags.delall("TALB")
            tags.add(TALB(encoding=3, text=album))
        # TCON: nombre legible del género (no el slug)
        tcon_text = _genre_name(genre_slug)
        if tcon_text:
            tags.delall("TCON")
            tags.add(TCON(encoding=3, text=tcon_text))
        # TDRC: year si está disponible
        if year:
            try:
                from mutagen.id3 import TDRC
                tags.delall("TDRC")
                tags.add(TDRC(encoding=3, text=year))
            except Exception:
                pass
        tags.save(path, v2_version=3)

    def _write_mp4(self, path: str, artist: str, title: str, genre_slug: str,
                   album: str = "", year: str = "") -> None:
        mp4 = MP4(path)
        mp4["\xa9ART"] = [artist]
        mp4["\xa9nam"] = [title]
        if album:
            mp4["\xa9alb"] = [album]
        tcon = _genre_name(genre_slug)
        if tcon:
            mp4["\xa9gen"] = [tcon]
        if year:
            mp4["\xa9day"] = [year]
        mp4.save()
