# mpc/curator/fixers/genres.py
# -*- coding: utf-8 -*-
"""
GenreFixer: mueve archivos a la carpeta correcta (por genre_slug) y/o
renombra al formato canónico `{artist} - {title}.{ext}`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from mpc.config import get_config
from mpc.curator.status import CuratorStatus
from mpc.library.repository import TrackRepository


from mpc.utils.text import canonical_filename as _canonical_filename


class GenreFixer:
    def __init__(self, repo: TrackRepository, music_dir: Optional[Path] = None):
        self.repo = repo
        self.music_dir = Path(music_dir or get_config().lib_base_dir)

    def run(self, dry_run: bool = False, auto: bool = True) -> dict:
        needs_move = self.repo.by_curator_status(CuratorStatus.NEEDS_MOVE)
        needs_rename = self.repo.by_curator_status(CuratorStatus.NEEDS_RENAME)

        total = len(needs_move) + len(needs_rename)
        if total == 0:
            print("✅ No hay archivos que mover ni renombrar.")
            return {"moved": 0, "renamed": 0, "failed": 0}

        moved = 0
        renamed = 0
        failed = 0

        for t in needs_move:
            result = self._move_to_genre(t, dry_run=dry_run, auto=auto)
            if result == "moved":
                moved += 1
            elif result == "failed":
                failed += 1

        for t in needs_rename:
            result = self._rename_canonical(t, dry_run=dry_run, auto=auto)
            if result == "renamed":
                renamed += 1
            elif result == "failed":
                failed += 1

        return {"moved": moved, "renamed": renamed, "failed": failed}

    def _move_to_genre(self, track: dict, dry_run: bool, auto: bool) -> str:
        fp = track.get("filepath") or ""
        genre = track.get("genre_slug") or ""
        if not fp or not os.path.isfile(fp) or not genre:
            return "skip"
        current_path = Path(fp)
        target_dir = self.music_dir / genre
        target = target_dir / current_path.name
        if current_path == target:
            return "skip"

        print(f"▶ MOVE {track['artist']} - {track['title']}")
        print(f"   {current_path}")
        print(f"   → {target}")

        if dry_run:
            return "skip"
        if not auto:
            try:
                resp = input("   Confirmar? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "skip"
            if resp == "n":
                return "skip"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current_path), str(target))
            update_kwargs = {
                "filepath": str(target),
                "genre_folder_ok": 1,
                "curator_status": (
                    CuratorStatus.OK if track.get("has_thumbnail") and track.get("has_valid_tags")
                    else CuratorStatus.NEEDS_THUMBNAIL if not track.get("has_thumbnail")
                    else CuratorStatus.NEEDS_TAGS
                ),
            }

            # NUEVO: mover MP4 asociado si existe
            bd_video = track.get("video_filepath") or ""
            if bd_video and os.path.isfile(bd_video):
                video_src = Path(bd_video)
                video_target = target_dir / video_src.name
                if video_src != video_target and not video_target.exists():
                    try:
                        shutil.move(str(video_src), str(video_target))
                        update_kwargs["video_filepath"] = str(video_target)
                        print(f"   ✅ video movido: {video_target.name}")
                    except Exception as e:
                        print(f"   ⚠️ video move error: {e}")

            self.repo.update_curator_flags(track["track_id"], **update_kwargs)
            print("   ✅ movido")
            return "moved"
        except Exception as e:
            print(f"   ❌ error: {e}")
            return "failed"

    def _rename_canonical(self, track: dict, dry_run: bool, auto: bool) -> str:
        fp = track.get("filepath") or ""
        if not fp or not os.path.isfile(fp):
            return "skip"
        current_path = Path(fp)
        new_name = _canonical_filename(
            track["artist"], track["title"], current_path.suffix
        )
        target = current_path.parent / new_name
        if current_path == target:
            return "skip"

        print(f"▶ RENAME {current_path.name} → {new_name}")

        if dry_run:
            return "skip"
        if not auto:
            try:
                resp = input("   Confirmar? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "skip"
            if resp == "n":
                return "skip"

        try:
            if target.exists():
                print(f"   ⚠️  target ya existe, saltando")
                return "skip"
            os.rename(str(current_path), str(target))
            self.repo.update_curator_flags(
                track["track_id"],
                filepath=str(target),
                filename_ok=1,
                curator_status=(
                    CuratorStatus.OK if track.get("has_thumbnail") and track.get("has_valid_tags")
                    else CuratorStatus.NEEDS_THUMBNAIL if not track.get("has_thumbnail")
                    else CuratorStatus.NEEDS_TAGS
                ),
            )
            print("   ✅ renombrado")
            return "renamed"
        except Exception as e:
            print(f"   ❌ error: {e}")
            return "failed"
