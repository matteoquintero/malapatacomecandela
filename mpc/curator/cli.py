# mpc/curator/cli.py
# -*- coding: utf-8 -*-
"""Handlers del subcomando `curator`."""

from __future__ import annotations

import argparse
from pathlib import Path

from mpc.config import get_config, PROJECT_DIR
from mpc.curator.auditor import Auditor
from mpc.curator.fixers import (
    AudioSourceBackfiller, DuplicateFixer, GenreFixer, MbidBackfiller,
    MetadataFixer, ReconcileFixer, TagFixer, ThumbnailFixer,
    VideoThumbnailFixer,
)
from mpc.library.repository import TrackRepository


def _repo() -> TrackRepository:
    db_path = str(PROJECT_DIR / "cache" / "library.db")
    return TrackRepository(db_path)


def cmd_audit(args: argparse.Namespace) -> None:
    cfg = get_config()
    music_dir = Path(cfg.lib_base_dir)
    print(f"🔍 Auditando {music_dir} vs cache/library.db...")
    auditor = Auditor(_repo(), music_dir)
    result = auditor.run()
    print(f"\n📊 Auditoría completa:")
    print(f"   BD total:            {result.db_total}")
    print(f"   Disco total:         {result.disk_total}")
    print(f"   Huérfanos creados:   {result.orphans_created}")
    print(f"   Tracks procesados:   {result.processed}")
    print(f"\n📋 Estado (curator_status):")
    for status, count in sorted(result.status_counts.items(), key=lambda x: -x[1]):
        print(f"   {status:<25} {count}")


def cmd_status(args: argparse.Namespace) -> None:
    repo = _repo()
    audio_counts = repo.count_by_curator_status()
    video_counts = repo.count_by_video_status()
    total = sum(audio_counts.values())
    if total == 0:
        print("📭 BD vacía. Corré `mala-pata curator audit` primero.")
        return

    print(f"\n📊 Estado AUDIO ({total} tracks):\n")
    for status, count in sorted(audio_counts.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        bar = "█" * int(pct / 3)
        print(f"   {status:<20} {count:>4}  {pct:>5.1f}%  {bar}")

    print(f"\n📺 Estado VIDEO ({total} tracks):\n")
    for status, count in sorted(video_counts.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        bar = "█" * int(pct / 3)
        print(f"   {status:<20} {count:>4}  {pct:>5.1f}%  {bar}")
    print()


def cmd_fix_thumbnails(args: argparse.Namespace) -> None:
    fixer = ThumbnailFixer(_repo())
    result = fixer.run(dry_run=args.dry_run, limit=args.limit)
    src = result.get("by_source", {})
    print(f"\n✨ Thumbnails:")
    print(f"   Total:       {result['total']}")
    print(f"   Reparados:   {result['fixed']}")
    print(f"   Fallidos:    {result['failed']}")
    print(f"   Por fuente:  CAA={src.get('caa',0)} audio={src.get('audio',0)} video={src.get('video',0)}")


def cmd_backfill_audio_source(args: argparse.Namespace) -> None:
    fixer = AudioSourceBackfiller(_repo())
    result = fixer.run(dry_run=args.dry_run, limit=args.limit, sleep_sec=args.sleep)
    print(f"\n✨ Backfill audio_source_id:")
    print(f"   Total:    {result['total']}")
    print(f"   Hallados: {result['found']}")
    print(f"   Fallidos: {result['failed']}")


def cmd_backfill_mbid(args: argparse.Namespace) -> None:
    fixer = MbidBackfiller(_repo())
    result = fixer.run(dry_run=args.dry_run, limit=args.limit, min_score=args.min_score)
    print(f"\n✨ Backfill mbid:")
    print(f"   Total:    {result['total']}")
    print(f"   Hallados: {result['found']}")
    print(f"   Fallidos: {result['failed']}")


def cmd_fix_metadata(args: argparse.Namespace) -> None:
    fixer = MetadataFixer(_repo())
    result = fixer.run(dry_run=args.dry_run, limit=args.limit)
    print(f"\n✨ Metadata:")
    print(f"   Total:          {result['total']}")
    print(f"   BD actualizados: {result.get('bd_updated', 0)}")
    print(f"   Renombrados:    {result.get('renamed', 0)}")
    print(f"   Tags escritos:  {result.get('tags_written', 0)}")
    print(f"   Saltados:       {result.get('skipped', 0)}")
    print(f"   Fallidos:       {result.get('failed', 0)}")


def cmd_fix_video_thumbnails(args: argparse.Namespace) -> None:
    fixer = VideoThumbnailFixer(_repo())
    result = fixer.run(dry_run=args.dry_run, limit=args.limit)
    print(f"\n✨ Video thumbnails (MP4 covr):")
    print(f"   Total:     {result['total']}")
    print(f"   Embebidos: {result.get('fixed', 0)}")
    print(f"   Saltados:  {result.get('skipped', 0)}")
    print(f"   Fallidos:  {result.get('failed', 0)}")


def cmd_audit_quality(args: argparse.Namespace) -> None:
    import os
    from mpc.curator.quality import QualityAnalyzer
    key = os.getenv("ACOUSTID_API_KEY", "")
    a = QualityAnalyzer(_repo(), acoustid_key=key)
    result = a.run(
        tier=args.tier, limit=args.limit,
        dry_run=args.dry_run, force=args.force,
    )
    print(f"\n✨ Calidad (tier {result['tier']}):")
    print(f"   Total:    {result['total']}")
    print(f"   OK:       {result['ok']}")
    print(f"   Fallidos: {result['failed']}")
    print(f"   Saltados: {result.get('skipped', 0)}")
    if result.get("by_score"):
        print(f"\n   Distribución de scores:")
        for band, n in result["by_score"].items():
            print(f"     {band:>6}: {n}")


def cmd_fix_tags(args: argparse.Namespace) -> None:
    fixer = TagFixer(_repo())
    result = fixer.run(dry_run=args.dry_run, limit=args.limit, use_mb=not args.no_mb)
    print(f"\n✨ Tags:")
    print(f"   Total:     {result['total']}")
    print(f"   Reparados: {result['fixed']}")
    print(f"   Fallidos:  {result['failed']}")


def cmd_fix_duplicates(args: argparse.Namespace) -> None:
    fixer = DuplicateFixer(_repo())
    result = fixer.run(
        dry_run=args.dry_run,
        auto=args.auto,
        by_fingerprint=getattr(args, "by_fingerprint", False),
    )
    print(f"\n✨ Duplicados:")
    print(f"   Grupos:          {result['groups']}")
    print(f"   Archivos borrados: {result['deleted']}")
    print(f"   Conservados:     {result['kept']}")
    print(f"   Saltados:        {result['skipped']}")


def cmd_fix_genres(args: argparse.Namespace) -> None:
    fixer = GenreFixer(_repo())
    result = fixer.run(dry_run=args.dry_run, auto=args.auto)
    print(f"\n✨ Géneros/Rename:")
    print(f"   Movidos:     {result['moved']}")
    print(f"   Renombrados: {result['renamed']}")
    print(f"   Fallidos:    {result['failed']}")


def cmd_reconcile(args: argparse.Namespace) -> None:
    fixer = ReconcileFixer(_repo())
    result = fixer.run(dry_run=args.dry_run, auto=args.auto)
    print(f"\n✨ Reconciliación:")
    print(f"   Huérfanos:    {result['orphans']} → resueltos: {result['orphans_resolved']}")
    print(f"   Fantasmas:    {result['missing']} → resueltos: {result['missing_resolved']}")


DISPATCH = {
    "audit": cmd_audit,
    "status": cmd_status,
    "fix-thumbnails": cmd_fix_thumbnails,
    "fix-tags": cmd_fix_tags,
    "fix-duplicates": cmd_fix_duplicates,
    "fix-genres": cmd_fix_genres,
    "fix-metadata": cmd_fix_metadata,
    "fix-video-thumbnails": cmd_fix_video_thumbnails,
    "reconcile": cmd_reconcile,
    "backfill-audio-source-id": cmd_backfill_audio_source,
    "backfill-mbid": cmd_backfill_mbid,
    "audit-quality": cmd_audit_quality,
}


def dispatch(args: argparse.Namespace) -> None:
    cmd = getattr(args, "curator_cmd", None)
    if not cmd:
        print("Uso: mala-pata curator {audit|status|fix-thumbnails|fix-tags|fix-duplicates|fix-genres|reconcile}")
        return
    handler = DISPATCH.get(cmd)
    if not handler:
        print(f"Subcomando desconocido: {cmd}")
        return
    handler(args)
