# mpc/curator/auditor.py
# -*- coding: utf-8 -*-
"""
Auditor: escanea disco + BD y pobla flags granulares en la tabla tracks.
Es READ-ONLY sobre archivos. Solo modifica la BD (columnas curator_*).
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mpc.curator.status import CuratorStatus, VideoStatus
from mpc.library.identity import track_id as make_track_id
from mpc.library.repository import TrackRepository
from mpc.utils.text import simp_pipeline, sanitize_filename_component, canonical_filename, nfc

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


def _is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS

JUNK_PATTERNS = [
    "(official video)", "(official music video)", "(official audio)",
    "[official video]", "[official audio]", "(lyrics)", "[lyrics]",
    "(hd)", "[hd]", "(4k)", "[4k]", "- youtube", "(audio)",
    "(video oficial)", "[video oficial]", "(lyric video)",
]


@dataclass
class DiskFile:
    path: Path
    rel_path: str
    genre_folder: str
    filename: str
    size_mb: float
    tag_artist: str = ""
    tag_title: str = ""
    tag_album: str = ""
    tag_genre: str = ""
    tag_year: str = ""
    has_thumbnail: bool = False
    fuzzy_key: str = ""
    issues: List[str] = field(default_factory=list)


@dataclass
class AuditResult:
    db_total: int
    disk_total: int
    processed: int
    orphans_created: int
    status_counts: Dict[str, int]


def _parse_filename(filename: str) -> Tuple[str, str]:
    stem = Path(filename).stem
    low = stem.lower()
    for jp in JUNK_PATTERNS:
        idx = low.find(jp)
        if idx != -1:
            stem = stem[:idx].strip(" -_")
            low = stem.lower()
    if " - " in stem:
        a, t = stem.split(" - ", 1)
        return a.strip(), t.strip()
    return "", stem.strip()


def _has_junk(filename: str) -> bool:
    low = filename.lower()
    return any(jp in low for jp in JUNK_PATTERNS)


def _read_metadata(f: DiskFile) -> None:
    if MutagenFile is None:
        return
    try:
        audio = MutagenFile(str(f.path))
        if audio is None:
            return
        if f.path.suffix.lower() == ".mp3":
            try:
                tags = ID3(str(f.path))
                f.tag_artist = str(tags.get("TPE1", "") or "").strip()
                f.tag_title = str(tags.get("TIT2", "") or "").strip()
                f.tag_album = str(tags.get("TALB", "") or "").strip()
                f.tag_genre = str(tags.get("TCON", "") or "").strip()
                f.tag_year = str(tags.get("TDRC", "") or "").strip()
                f.has_thumbnail = any(
                    isinstance(v, APIC)
                    or (hasattr(v, "FrameID") and v.FrameID == "APIC")
                    for v in tags.values()
                )
                return
            except Exception:
                pass
        tags_dict = getattr(audio, "tags", None) or {}

        def _g(*keys):
            for k in keys:
                v = tags_dict.get(k) if hasattr(tags_dict, "get") else None
                if v:
                    return str(v[0] if isinstance(v, list) else v).strip()
            return ""

        f.tag_artist = _g("artist", "©ART", "TPE1")
        f.tag_title = _g("title", "©nam", "TIT2")
        f.tag_album = _g("album", "©alb", "TALB")
        f.tag_genre = _g("genre", "©gen", "TCON")
        f.tag_year = _g("date", "©day", "TDRC")
        f.has_thumbnail = bool(
            tags_dict.get("covr") if hasattr(tags_dict, "get") else False
        )
    except Exception:
        pass


def _scan_disk(music_dir: Path) -> Tuple[List[DiskFile], List[DiskFile]]:
    """Escanea y separa audios de videos. Devuelve (audios, videos)."""
    audios: List[DiskFile] = []
    videos: List[DiskFile] = []
    for path in sorted(music_dir.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in ALL_EXTS:
            continue
        rel = path.relative_to(music_dir)
        parts = rel.parts
        genre_folder = parts[0] if len(parts) > 1 else ""
        df = DiskFile(
            path=path,
            rel_path=str(rel),
            genre_folder=genre_folder,
            filename=path.name,
            size_mb=round(path.stat().st_size / (1024 * 1024), 2),
        )
        if ext in AUDIO_EXTS:
            _read_metadata(df)

        fn_a, fn_t = _parse_filename(df.filename)
        # Usa track_id() (normalización estricta sin guiones/puntuación) para que
        # la fuzzy_key matchee con los track_ids de BD.
        if df.tag_artist and df.tag_title:
            df.fuzzy_key = make_track_id(df.tag_artist, df.tag_title)
        elif fn_a and fn_t:
            df.fuzzy_key = make_track_id(fn_a, fn_t)

        if ext in AUDIO_EXTS:
            audios.append(df)
        else:
            videos.append(df)
    return audios, videos


# _canonical_filename: ahora importado desde mpc.utils.text.canonical_filename (SSOT)


class Auditor:
    """Corre una auditoría completa y actualiza las columnas curator_* en BD."""

    def __init__(self, repo: TrackRepository, music_dir: Path):
        self.repo = repo
        self.music_dir = Path(music_dir)

    def run(self) -> AuditResult:
        if MutagenFile is None:
            raise RuntimeError("mutagen no está instalado. pip install mutagen")

        db = self.repo.get_all()
        db_by_tid: Dict[str, dict] = {t["track_id"]: t for t in db}

        audios, videos = _scan_disk(self.music_dir)

        # Agrupa audios por fuzzy_key (para detección de duplicados reales de audio)
        by_fuzzy: Dict[str, List[DiskFile]] = defaultdict(list)
        for f in audios:
            if f.fuzzy_key:
                by_fuzzy[f.fuzzy_key].append(f)

        # Agrupa videos por fuzzy_key (para asociar video_filepath al track)
        videos_by_fuzzy: Dict[str, List[DiskFile]] = defaultdict(list)
        for v in videos:
            if v.fuzzy_key:
                videos_by_fuzzy[v.fuzzy_key].append(v)

        disk_keys = set(by_fuzzy.keys())

        # Primero: marcar todos los tracks de la BD
        orphans_created = 0
        for t in db:
            tid = t["track_id"]
            self._audit_db_track(t, by_fuzzy, disk_keys, videos_by_fuzzy)

        # Segundo: detectar huérfanos de AUDIO (MP3 en disco sin track en BD)
        for f in audios:
            if not f.fuzzy_key:
                continue
            if f.fuzzy_key in db_by_tid:
                continue
            self._insert_orphan_from_file(f)
            orphans_created += 1

        # Tercero: detectar huérfanos de VIDEO (MP4 en disco sin track ni audio en BD)
        # Re-leer db_by_tid para incluir orphans de audio recién insertados
        db_after = self.repo.get_all()
        db_tids_now = {t["track_id"] for t in db_after}
        for v in videos:
            if not v.fuzzy_key:
                continue
            if v.fuzzy_key in db_tids_now:
                continue
            # MP4 sin match ni en audio ni en BD
            fn_a, fn_t = _parse_filename(v.filename)
            artist = v.tag_artist or fn_a or "Unknown"
            title = v.tag_title or fn_t or v.filename
            self.repo.insert_video_orphan(
                artist=artist, title=title,
                video_filepath=str(v.path),
                genre_slug=v.genre_folder or "",
            )
            orphans_created += 1

        counts = self.repo.count_by_curator_status()
        return AuditResult(
            db_total=len(db),
            disk_total=len(audios) + len(videos),
            processed=len(db) + orphans_created,
            orphans_created=orphans_created,
            status_counts=counts,
        )

    def _audit_db_track(
        self,
        track: dict,
        by_fuzzy: Dict[str, List[DiskFile]],
        disk_keys: set,
        videos_by_fuzzy: Optional[Dict[str, List[DiskFile]]] = None,
    ) -> None:
        tid = track["track_id"]
        candidates = by_fuzzy.get(tid, [])

        if not candidates:
            # MISSING: en BD pero no en disco. video_status queda NOT_READY.
            prev_vs = track.get("video_status")
            video_status = prev_vs if prev_vs in VideoStatus.TERMINAL else VideoStatus.NOT_READY
            self.repo.update_curator_flags(
                tid,
                has_thumbnail=0,
                has_valid_tags=0,
                filename_ok=0,
                genre_folder_ok=0,
                curator_status=CuratorStatus.MISSING,
                video_status=video_status,
            )
            return

        # Seleccionar el mejor candidato (prioridad: mismo género BD)
        matched = self._best_match(candidates, track.get("genre_slug") or "")

        # Calcular flags — comparaciones normalizadas a NFC (fix macOS NFD)
        ext = Path(matched.filename).suffix.lower() or ".mp3"
        expected_name = canonical_filename(track["artist"], track["title"], ext)
        filename_ok = 1 if nfc(matched.filename) == expected_name else 0

        genre_slug = (track.get("genre_slug") or "").strip()
        genre_folder_ok = 1 if (
            genre_slug and matched.genre_folder == genre_slug
        ) else 0

        has_thumb = 1 if matched.has_thumbnail else 0
        has_valid_tags = 1 if (
            matched.tag_artist and matched.tag_title and matched.tag_album
        ) else 0

        # Metadata consistency: tag y filename deben matchear BD exacto (NFC).
        # Nota: TALB (álbum) NO se valida aquí — es nombre real, resuelto via
        # AlbumResolver (MB/Discogs/LLM). fix-metadata se encarga de llenarlo.
        exp_artist = sanitize_filename_component(track["artist"])
        exp_title = sanitize_filename_component(track["title"])
        metadata_consistent = 1
        if matched.tag_artist and nfc(matched.tag_artist) != exp_artist:
            metadata_consistent = 0
        if matched.tag_title and nfc(matched.tag_title) != exp_title:
            metadata_consistent = 0
        if not filename_ok:
            metadata_consistent = 0

        # Duplicado? Este grupo tiene >1 archivo?
        is_dup_group = len(candidates) > 1
        is_duplicate_of = None

        # Determinar curator_status por prioridad.
        # Si hay 2+ archivos en disco con el mismo track_id, el row se marca
        # duplicate sin importar cuál sea el "matched" — resolverlo requiere
        # `curator fix-duplicates`. Después del fix, el auditor re-clasifica.
        if is_dup_group:
            curator_status = CuratorStatus.DUPLICATE
            if matched is not candidates[0]:
                is_duplicate_of = candidates[0].fuzzy_key
        else:
            curator_status = self._classify(
                has_thumb, has_valid_tags, filename_ok, genre_folder_ok, track
            )

        # Actualizar filepath si difiere
        new_filepath = str(matched.path)
        actual_fp = track.get("filepath") or ""

        # Asociar video_filepath si hay un video con el mismo fuzzy_key
        video_filepath_new = None
        if videos_by_fuzzy is not None:
            vids = videos_by_fuzzy.get(tid, [])
            if vids:
                video_filepath_new = str(vids[0].path)

        # Limpieza: si BD tiene video_filepath pero el archivo ya no existe,
        # limpiar el campo (no mentir en BD).
        bd_video_fp = track.get("video_filepath") or ""
        if bd_video_fp and not os.path.isfile(bd_video_fp) and not video_filepath_new:
            # Marcar para clear — update_kwargs se arma después
            video_filepath_cleared = True
        else:
            video_filepath_cleared = False

        # Si no es duplicate/missing y metadata inconsistente → needs_metadata
        if not is_dup_group and metadata_consistent == 0:
            if curator_status in (CuratorStatus.OK, CuratorStatus.NEEDS_THUMBNAIL, CuratorStatus.NEEDS_TAGS):
                curator_status = CuratorStatus.NEEDS_METADATA

        update_kwargs = {
            "has_thumbnail": has_thumb,
            "has_valid_tags": has_valid_tags,
            "filename_ok": filename_ok,
            "genre_folder_ok": genre_folder_ok,
            "is_duplicate_of": is_duplicate_of,
            "curator_status": curator_status,
            "metadata_consistent": metadata_consistent,
            "album": matched.tag_album or track.get("album") or "",
            "year": matched.tag_year or track.get("year") or "",
        }
        if actual_fp != new_filepath:
            update_kwargs["filepath"] = new_filepath
        if track.get("status") != "downloaded":
            update_kwargs["status"] = "downloaded"
        if not track.get("genre_slug") and matched.genre_folder:
            update_kwargs["genre_slug"] = matched.genre_folder
        if video_filepath_new and video_filepath_new != (track.get("video_filepath") or ""):
            update_kwargs["video_filepath"] = video_filepath_new
        elif video_filepath_cleared:
            update_kwargs["video_filepath"] = ""

        # Decidir video_status (independiente del curator_status)
        prev_vs = track.get("video_status")
        effective_video_fp = video_filepath_new or track.get("video_filepath") or ""
        video_exists = bool(effective_video_fp and os.path.isfile(effective_video_fp))
        if prev_vs in VideoStatus.TERMINAL:
            video_status = prev_vs  # preservar rejected/unavailable
        elif video_exists:
            video_status = VideoStatus.VIDEO_OK
        elif curator_status != CuratorStatus.OK:
            video_status = VideoStatus.NOT_READY
        else:
            video_status = VideoStatus.NEEDS_VIDEO
        update_kwargs["video_status"] = video_status

        self.repo.update_curator_flags(tid, **update_kwargs)

    def _best_match(
        self, candidates: List[DiskFile], expected_genre: str
    ) -> DiskFile:
        """Elige el mejor candidato: prefiere mismo género, luego con thumbnail,
        luego más acentos, luego más grande."""

        def score(f: DiskFile) -> tuple:
            same_genre = 1 if (expected_genre and f.genre_folder == expected_genre) else 0
            accent_count = sum(1 for c in f.filename if ord(c) > 127)
            junk = sum(1 for p in JUNK_PATTERNS if p in f.filename.lower())
            return (
                same_genre,
                int(f.has_thumbnail),
                accent_count,
                f.size_mb,
                -junk,
            )

        return max(candidates, key=score)

    def _classify(
        self,
        has_thumb: int,
        has_valid_tags: int,
        filename_ok: int,
        genre_folder_ok: int,
        track: dict,
    ) -> str:
        if not genre_folder_ok and track.get("genre_slug"):
            return CuratorStatus.NEEDS_MOVE
        if not filename_ok:
            return CuratorStatus.NEEDS_RENAME
        if not has_thumb:
            return CuratorStatus.NEEDS_THUMBNAIL
        if not has_valid_tags:
            return CuratorStatus.NEEDS_TAGS
        return CuratorStatus.OK

    def _insert_orphan_from_file(self, f: DiskFile) -> None:
        fn_a, fn_t = _parse_filename(f.filename)
        artist = f.tag_artist or fn_a or "Unknown"
        title = f.tag_title or fn_t or f.filename
        self.repo.insert_orphan(
            artist=artist,
            title=title,
            filepath=str(f.path),
            genre_slug=f.genre_folder or "",
            album=f.tag_album,
            year=f.tag_year,
            has_thumbnail=int(f.has_thumbnail),
        )

