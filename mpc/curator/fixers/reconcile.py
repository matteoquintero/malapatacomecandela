# mpc/curator/fixers/reconcile.py
# -*- coding: utf-8 -*-
"""
ReconcileFixer: resuelve huérfanos (en disco, no en BD) y fantasmas (en BD,
no en disco). Interactivo por default.
"""

from __future__ import annotations

import os
from typing import Optional

from mpc.curator.status import CuratorStatus
from mpc.library.repository import TrackRepository


class ReconcileFixer:
    def __init__(self, repo: TrackRepository):
        self.repo = repo

    def run(self, dry_run: bool = False, auto: bool = False) -> dict:
        orphans = self.repo.by_curator_status(CuratorStatus.ORPHAN)
        missing = self.repo.by_curator_status(CuratorStatus.MISSING)
        # Separar audio vs video orphans (video orphans tienen filepath vacío)
        audio_orphans = [o for o in orphans if o.get("filepath")]
        video_orphans = [o for o in orphans if not o.get("filepath")
                         and o.get("video_filepath")]
        video_stale = self.repo.video_stale()

        print(f"\n📋 Reconciliación:")
        print(f"   📊 AUDIO:")
        print(f"      Huérfanos:  {len(audio_orphans)}")
        print(f"      Fantasmas:  {len(missing)}")
        print(f"   📺 VIDEO:")
        print(f"      Huérfanos:  {len(video_orphans)}")
        print(f"      Stale:      {len(video_stale)}\n")

        orph_resolved = self._process_orphans(audio_orphans, dry_run=dry_run, auto=auto)
        miss_resolved = self._process_missing(missing, dry_run=dry_run, auto=auto)
        vorph_resolved = self._process_video_orphans(video_orphans, dry_run=dry_run, auto=auto)
        vstale_resolved = self._process_video_stale(video_stale, dry_run=dry_run, auto=auto)

        return {
            "orphans": len(audio_orphans),
            "orphans_resolved": orph_resolved,
            "missing": len(missing),
            "missing_resolved": miss_resolved,
            "video_orphans": len(video_orphans),
            "video_orphans_resolved": vorph_resolved,
            "video_stale": len(video_stale),
            "video_stale_resolved": vstale_resolved,
        }

    def _process_orphans(self, orphans: list, dry_run: bool, auto: bool) -> int:
        resolved = 0
        for t in orphans:
            label = f"{t['artist']} - {t['title']}"
            print(f"\n🆕 HUÉRFANO: {label}")
            print(f"   path: {t.get('filepath')}")
            print(f"   genre: {t.get('genre_slug')}")

            if dry_run:
                continue

            if auto:
                # Auto: aceptar (ya está insertado como orphan, solo cambiar a ok/needs_*)
                action = "a"
            else:
                try:
                    action = input(
                        "   (a)ccept (mantener en BD) / (d)elete archivo / (s)kip: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break

            if action == "a":
                # Re-clasificar según flags existentes
                has_t = t.get("has_thumbnail")
                has_tg = t.get("has_valid_tags")
                if has_t and has_tg:
                    new_status = CuratorStatus.OK
                elif not has_t:
                    new_status = CuratorStatus.NEEDS_THUMBNAIL
                else:
                    new_status = CuratorStatus.NEEDS_TAGS
                self.repo.update_curator_flags(
                    t["track_id"],
                    curator_status=new_status,
                    status="downloaded",
                )
                print(f"   ✅ aceptado como {new_status}")
                resolved += 1
            elif action == "d":
                try:
                    if t.get("filepath") and os.path.isfile(t["filepath"]):
                        os.remove(t["filepath"])
                    self.repo.delete_track(t["track_id"])
                    print("   🗑  archivo y fila borrados")
                    resolved += 1
                except Exception as e:
                    print(f"   ❌ error: {e}")
        return resolved

    def _process_missing(self, missing: list, dry_run: bool, auto: bool) -> int:
        resolved = 0
        for t in missing:
            label = f"{t['artist']} - {t['title']}"
            print(f"\n👻 FANTASMA: {label}")
            print(f"   genre: {t.get('genre_slug')} / audio_src: {t.get('audio_source_id') or '—'}")

            if dry_run:
                continue

            if auto:
                # Auto: marcar como pending para re-descarga
                action = "p"
            else:
                try:
                    action = input(
                        "   (p)ending para re-descargar / (d)elete de BD / (s)kip: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break

            if action == "p":
                self.repo.update_curator_flags(
                    t["track_id"],
                    status="pending",
                    curator_status=CuratorStatus.MISSING,
                )
                print("   ✅ marcada como pending")
                resolved += 1
            elif action == "d":
                try:
                    self.repo.delete_track(t["track_id"])
                    print("   🗑  fila borrada de BD")
                    resolved += 1
                except Exception as e:
                    print(f"   ❌ error: {e}")
        return resolved

    def _process_video_orphans(self, orphans: list, dry_run: bool, auto: bool) -> int:
        """MP4 en disco sin audio correspondiente."""
        resolved = 0
        for t in orphans:
            label = f"{t['artist']} - {t['title']}"
            print(f"\n🆕 VIDEO HUÉRFANO: {label}")
            print(f"   mp4: {t.get('video_filepath')}")

            if dry_run:
                continue
            if auto:
                action = "a"
            else:
                try:
                    action = input(
                        "   (a)ccept (mantener en BD) / (d)elete archivo / (s)kip: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break

            if action == "a":
                from mpc.curator.status import VideoStatus
                self.repo.update_curator_flags(
                    t["track_id"],
                    curator_status=CuratorStatus.OK,
                    video_status=VideoStatus.VIDEO_OK,
                )
                print("   ✅ aceptado")
                resolved += 1
            elif action == "d":
                try:
                    if t.get("video_filepath") and os.path.isfile(t["video_filepath"]):
                        os.remove(t["video_filepath"])
                    self.repo.delete_track(t["track_id"])
                    print("   🗑  MP4 y fila borrados")
                    resolved += 1
                except Exception as e:
                    print(f"   ❌ error: {e}")
        return resolved

    def _process_video_stale(self, stale: list, dry_run: bool, auto: bool) -> int:
        """BD dice video_filepath=X pero X no existe en disco."""
        resolved = 0
        for t in stale:
            label = f"{t['artist']} - {t['title']}"
            print(f"\n👻 VIDEO STALE: {label}")
            print(f"   BD dice: {t.get('video_filepath')}")
            print(f"   Disco: (inexistente)")

            if dry_run:
                continue
            if auto:
                action = "c"
            else:
                try:
                    action = input(
                        "   (c)lear campo BD / (s)kip: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break

            if action == "c":
                from mpc.curator.status import VideoStatus
                self.repo.update_curator_flags(
                    t["track_id"],
                    video_filepath="",
                    video_status=VideoStatus.NEEDS_VIDEO,
                )
                print("   ✅ video_filepath limpiado")
                resolved += 1
        return resolved
