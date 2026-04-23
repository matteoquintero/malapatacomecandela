# mpc/curator/fixers/duplicates.py
# -*- coding: utf-8 -*-
"""
DuplicateFixer: detecta y borra archivos duplicados en disco conservando el
mejor candidato.

Agrupa archivos por fuzzy_key (simp(artist)|simp(title)) a partir de tag o
filename. Un grupo con 2+ archivos es un duplicado.

Heurística: thumb → tags válidos → acentos → tamaño → menos junk.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mpc.config import get_config
from mpc.curator.status import CuratorStatus
from mpc.library.repository import TrackRepository
from mpc.library.identity import track_id as _track_id

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, APIC
except ImportError:
    MutagenFile = None
    ID3 = None
    APIC = None


AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".opus", ".ogg"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm"}
ALL_EXTS = AUDIO_EXTS | VIDEO_EXTS


def _media_type(ext: str) -> str:
    ext = ext.lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "other"

JUNK_PATTERNS = [
    "(official video)", "(official music video)", "(official audio)",
    "[official video]", "[official audio]", "(lyrics)", "[lyrics]",
    "(hd)", "[hd]", "(4k)", "[4k]", "- youtube", "(audio)",
    "(video oficial)", "[video oficial]", "(lyric video)",
]


class _FileInfo:
    """Metadata mínima de un archivo para scoring de duplicados."""
    __slots__ = (
        "path", "filename", "size", "has_thumbnail", "has_valid_tags",
        "fuzzy_key", "tag_artist", "tag_title", "accents",
    )

    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name
        try:
            self.size = path.stat().st_size
        except OSError:
            self.size = 0
        self.has_thumbnail = False
        self.has_valid_tags = False
        self.tag_artist = ""
        self.tag_title = ""
        self.fuzzy_key = ""
        self.accents = sum(1 for c in self.filename if ord(c) > 127)
        self._read_tags()
        self._compute_fuzzy_key()

    def _read_tags(self) -> None:
        if MutagenFile is None:
            return
        try:
            if self.path.suffix.lower() == ".mp3":
                tags = ID3(str(self.path))
                self.tag_artist = str(tags.get("TPE1", "") or "").strip()
                self.tag_title = str(tags.get("TIT2", "") or "").strip()
                album = str(tags.get("TALB", "") or "").strip()
                self.has_valid_tags = bool(
                    self.tag_artist and self.tag_title and album
                )
                self.has_thumbnail = any(
                    isinstance(v, APIC)
                    or (hasattr(v, "FrameID") and v.FrameID == "APIC")
                    for v in tags.values()
                )
        except Exception:
            pass

    def _compute_fuzzy_key(self) -> None:
        # Usa track_id() (normalización estricta sin guiones/puntuación) para
        # que matchee con los track_ids de BD y con el auditor.
        if self.tag_artist and self.tag_title:
            self.fuzzy_key = _track_id(self.tag_artist, self.tag_title)
            return
        stem = self.path.stem
        low = stem.lower()
        for jp in JUNK_PATTERNS:
            idx = low.find(jp)
            if idx != -1:
                stem = stem[:idx].strip(" -_")
                low = stem.lower()
        if " - " in stem:
            a, t = stem.split(" - ", 1)
            self.fuzzy_key = _track_id(a.strip(), t.strip())

    def junk_count(self) -> int:
        low = self.filename.lower()
        return sum(1 for p in JUNK_PATTERNS if p in low)

    def score(self) -> tuple:
        return (
            int(self.has_thumbnail),
            int(self.has_valid_tags),
            self.accents,
            self.size,
            -self.junk_count(),
        )


class DuplicateFixer:
    """
    Escanea el directorio musical completo, detecta archivos con el mismo
    fuzzy_key (2+ archivos del mismo track) y elimina los peores.
    """

    def __init__(self, repo: TrackRepository, music_dir: Optional[Path] = None):
        self.repo = repo
        self.music_dir = Path(music_dir or get_config().lib_base_dir)

    def _scan(self) -> List[_FileInfo]:
        files: List[_FileInfo] = []
        for path in sorted(self.music_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ALL_EXTS:
                continue
            files.append(_FileInfo(path))
        return files

    def run(
        self,
        dry_run: bool = False,
        auto: bool = False,
        by_fingerprint: bool = False,
    ) -> dict:
        if MutagenFile is None:
            print("❌ mutagen no disponible")
            return {"groups": 0, "deleted": 0, "kept": 0, "skipped": 0}

        if by_fingerprint:
            return self._run_by_fingerprint(dry_run=dry_run, auto=auto)

        files = self._scan()
        # Agrupar por (fuzzy_key, media_type) para que MP3+MP4 no cuenten como dup.
        groups: Dict[tuple, List[_FileInfo]] = defaultdict(list)
        for f in files:
            if f.fuzzy_key:
                media = _media_type(f.path.suffix)
                groups[(f.fuzzy_key, media)].append(f)

        dup_groups = [g for g in groups.values() if len(g) > 1]

        if not dup_groups:
            print("✅ No hay duplicados detectados.")
            return {"groups": 0, "deleted": 0, "kept": 0, "skipped": 0}

        print(f"🔍 {len(dup_groups)} grupos de duplicados detectados.\n")

        deleted = 0
        kept = 0
        skipped = 0

        for gi, group in enumerate(dup_groups, 1):
            sorted_grp = sorted(group, key=lambda f: f.score(), reverse=True)
            winner = sorted_grp[0]
            losers = sorted_grp[1:]
            media = _media_type(winner.path.suffix)

            print(f"━━━ Grupo {gi} [{media}]: {winner.fuzzy_key} ━━━")
            self._print_file("✅ GANADOR", winner)
            for L in losers:
                self._print_file("❌ BORRAR", L)

            if dry_run:
                print("  [DRY-RUN] nada se borra\n")
                skipped += len(losers)
                continue

            if not auto:
                try:
                    resp = input("  Confirmar borrado? [Y/n/q]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n⚠️  Interrumpido.")
                    break
                if resp == "q":
                    break
                if resp == "n":
                    skipped += len(losers)
                    print()
                    continue

            # Borrar los losers y actualizar BD si la filepath apunta a un loser
            winner_rel = str(winner.path)
            tid = winner.fuzzy_key
            for L in losers:
                try:
                    os.remove(str(L.path))
                    print(f"    🗑  borrado {L.filename}")
                    deleted += 1
                except Exception as e:
                    print(f"    ⚠️  error borrando {L.filename}: {e}")

            # Si la BD apuntaba al loser, actualizar al winner
            row = None
            with self.repo._conn() as con:
                row = con.execute(
                    "SELECT track_id, filepath FROM tracks WHERE track_id=?",
                    (tid,),
                ).fetchone()
                if row and row["filepath"] != winner_rel:
                    con.execute(
                        "UPDATE tracks SET filepath=?, updated_at=datetime('now') "
                        "WHERE track_id=?",
                        (winner_rel, tid),
                    )
                    print(f"    🔄 BD actualizada al archivo ganador")

            # Recalcular curator_status del winner
            self.repo.update_curator_flags(
                tid,
                filepath=winner_rel,
                has_thumbnail=int(winner.has_thumbnail),
                has_valid_tags=int(winner.has_valid_tags),
                is_duplicate_of=None,
                curator_status=(
                    CuratorStatus.OK if winner.has_thumbnail and winner.has_valid_tags
                    else CuratorStatus.NEEDS_TAGS if winner.has_thumbnail
                    else CuratorStatus.NEEDS_THUMBNAIL
                ),
            )
            kept += 1
            print()

        return {
            "groups": len(dup_groups),
            "deleted": deleted,
            "kept": kept,
            "skipped": skipped,
        }

    def _run_by_fingerprint(self, dry_run: bool, auto: bool) -> dict:
        """Agrupa por audio_fingerprint (tier 3 de audit-quality debe haberse corrido)."""
        import os as _os
        groups = self.repo.audio_duplicates_by_fingerprint()
        if not groups:
            print("✅ No hay duplicados por fingerprint. (Corré `curator audit-quality --tier 3` primero si no lo hiciste)")
            return {"groups": 0, "deleted": 0, "kept": 0, "skipped": 0}

        print(f"🔍 {len(groups)} grupos de duplicados por FINGERPRINT detectados.\n")
        deleted = kept = skipped = 0

        for gi, group in enumerate(groups, 1):
            # Ganador: mayor audio_quality_score
            sorted_grp = sorted(
                group,
                key=lambda t: (t.get("audio_quality_score") or 0, t.get("bitrate_kbps") or 0),
                reverse=True,
            )
            winner = sorted_grp[0]
            losers = sorted_grp[1:]

            print(f"━━━ Grupo {gi} [fingerprint] ━━━")
            print(f"  ✅ GANADOR: {winner['filepath']}  "
                  f"[score={winner.get('audio_quality_score','?')}, br={winner.get('bitrate_kbps','?')}k]")
            for L in losers:
                print(f"  ❌ BORRAR: {L['filepath']}  "
                      f"[score={L.get('audio_quality_score','?')}, br={L.get('bitrate_kbps','?')}k]")

            if dry_run:
                print("  [DRY-RUN] nada se borra\n")
                skipped += len(losers)
                continue

            if not auto:
                try:
                    resp = input("  Confirmar borrado? [Y/n/q]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break
                if resp == "q":
                    break
                if resp == "n":
                    skipped += len(losers)
                    continue

            for L in losers:
                try:
                    if L.get("filepath") and _os.path.isfile(L["filepath"]):
                        _os.remove(L["filepath"])
                    self.repo.delete_track(L["track_id"])
                    print(f"    🗑  {_os.path.basename(L['filepath'])}")
                    deleted += 1
                except Exception as e:
                    print(f"    ⚠️  {e}")
            kept += 1
            print()

        return {"groups": len(groups), "deleted": deleted, "kept": kept, "skipped": skipped}

    def _print_file(self, tag: str, f: _FileInfo) -> None:
        size_mb = f.size / (1024 * 1024)
        flags = []
        flags.append("thumb" if f.has_thumbnail else "no-thumb")
        flags.append("tags" if f.has_valid_tags else "no-tags")
        flags.append(f"{f.accents}acc")
        flags_s = " ".join(flags)
        rel = f.path
        try:
            rel = f.path.relative_to(self.music_dir)
        except ValueError:
            pass
        print(f"  {tag}: {rel}  [{size_mb:.1f}MB, {flags_s}]")
