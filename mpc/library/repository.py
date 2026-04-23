# mpc/library/repository.py
# -*- coding: utf-8 -*-
"""
TrackRepository: fuente de verdad de la colección.

SQLite con schema extendido para:
  - Consultas reales (by_artist, by_genre, failed, by_curator_status)
  - Resume: saber exactamente qué descargué y en qué estado
  - Historial de errores por track
  - Fuentes separadas: audio_source_* (MP3) y video_source_* (MP4)
  - Metadatos de discovery (confidence, evidence, MBID)
  - Curator flags: has_thumbnail, has_valid_tags, filename_ok, genre_folder_ok,
    curator_status, is_duplicate_of
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from mpc.library.identity import track_id

logger = logging.getLogger("mpc.library.repository")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id     TEXT UNIQUE NOT NULL,
    artist       TEXT NOT NULL,
    title        TEXT NOT NULL,
    mbid         TEXT,
    audio_source_id       TEXT,
    audio_source_platform TEXT,
    video_source_id       TEXT,
    platform     TEXT,
    genre_slug   TEXT,
    filepath     TEXT,
    video_filepath TEXT,
    status       TEXT NOT NULL,
    error_detail TEXT,
    confidence   REAL,
    evidence     TEXT,
    has_thumbnail      INTEGER,
    has_valid_tags     INTEGER,
    filename_ok        INTEGER,
    genre_folder_ok    INTEGER,
    is_duplicate_of    TEXT,
    curator_status     TEXT,
    curator_checked_at TEXT,
    album              TEXT,
    year               TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artist          ON tracks(artist COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_genre           ON tracks(genre_slug);
CREATE INDEX IF NOT EXISTS idx_status          ON tracks(status);
"""

# Columnas del flujo antiguo `doctor` — DROP si existen.
_DEPRECATED_COLUMNS = [
    "needs_video_review",
    "video_review_status",
    "video_reviewed_at",
    "video_skip_reason",
]

# Columnas aditivas que pueden faltar en BDs viejas.
_ADDITIVE_COLUMNS = [
    # curator
    ("has_thumbnail",            "INTEGER"),
    ("has_valid_tags",           "INTEGER"),
    ("filename_ok",              "INTEGER"),
    ("genre_folder_ok",          "INTEGER"),
    ("is_duplicate_of",          "TEXT"),
    ("curator_status",           "TEXT"),
    ("curator_checked_at",       "TEXT"),
    ("album",                    "TEXT"),
    ("year",                     "TEXT"),
    # fuentes separadas (audio/video)
    ("audio_source_id",          "TEXT"),
    ("audio_source_platform",    "TEXT"),
    ("audio_source_title",       "TEXT"),
    ("audio_source_channel",     "TEXT"),
    ("audio_source_duration",    "INTEGER"),
    ("audio_source_fetched_at",  "TEXT"),
    ("video_source_id",          "TEXT"),
    ("video_source_platform",    "TEXT"),
    ("video_source_title",       "TEXT"),
    ("video_source_channel",     "TEXT"),
    ("video_source_duration",    "INTEGER"),
    ("video_source_fetched_at",  "TEXT"),
    # MusicBrainz metadata
    ("mbid_score",               "INTEGER"),
    ("mb_fetched_at",            "TEXT"),
    # metadata-consistency
    ("metadata_consistent",      "INTEGER"),
    ("has_video_thumbnail",      "INTEGER"),
    # video-status-separate
    ("video_status",             "TEXT"),
    # audio-quality-analyzer
    ("bitrate_kbps",             "INTEGER"),
    ("sample_rate",              "INTEGER"),
    ("codec",                    "TEXT"),
    ("channels",                 "INTEGER"),
    ("duration_sec",             "REAL"),
    ("lufs_integrated",          "REAL"),
    ("true_peak_db",             "REAL"),
    ("dynamic_range",            "REAL"),
    ("audio_fingerprint",        "TEXT"),
    ("acoustid_mbid",            "TEXT"),
    ("audio_quality_score",      "INTEGER"),
    ("audio_quality_checked_at", "TEXT"),
]


class TrackRepository:
    """
    Repositorio SQLite de tracks descargados / intentados.

    Thread-safe: cada llamada abre una conexión corta (WAL mode).
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as con:
            con.executescript(_SCHEMA)
            existing = {
                r[1] for r in con.execute("PRAGMA table_info(tracks)").fetchall()
            }
            # Migración 1: rename video_id → video_source_id (SQLite 3.25+)
            if "video_id" in existing and "video_source_id" not in existing:
                con.execute(
                    "ALTER TABLE tracks RENAME COLUMN video_id TO video_source_id"
                )
                existing.discard("video_id")
                existing.add("video_source_id")
            # Migración 2: agrega columnas curator_* + source nuevos si faltan.
            for col_name, col_type in _ADDITIVE_COLUMNS:
                if col_name not in existing:
                    con.execute(
                        f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}"
                    )
            # Migración 3: elimina columnas deprecated (SQLite 3.35+).
            for col in _DEPRECATED_COLUMNS:
                if col in existing:
                    try:
                        con.execute(f"ALTER TABLE tracks DROP COLUMN {col}")
                    except sqlite3.OperationalError:
                        pass
            # Índices (todos idempotentes).
            con.execute(
                "DROP INDEX IF EXISTS idx_video_pending"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_video_source_pending "
                "ON tracks(video_source_id, video_filepath)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_audio_source "
                "ON tracks(audio_source_id)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_curator_status "
                "ON tracks(curator_status)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_duplicate_of "
                "ON tracks(is_duplicate_of)"
            )

    # ── Conexión ──────────────────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # ── Escritura ─────────────────────────────────────────────────────────────

    def record(
        self,
        artist: str,
        title: str,
        audio_source_id: str = "",
        audio_source_platform: str = "",
        video_source_id: str = "",
        platform: str = "",
        genre_slug: str = "",
        filepath: str = "",
        status: str = "downloaded",
        error_detail: str = "",
        confidence: float = 0.0,
        evidence: Optional[List[str]] = None,
        mbid: Optional[str] = None,
        # retrocompat: parametros viejos
        video_id: Optional[str] = None,
    ) -> None:
        """Inserta o actualiza un track. UPSERT por track_id.

        `video_id` (deprecated) se mapea a `audio_source_id` si no se provee
        explícitamente — el pipeline viejo lo usaba con semántica audio.
        """
        if video_id is not None and not audio_source_id:
            import warnings
            warnings.warn(
                "video_id está deprecated, usar audio_source_id",
                DeprecationWarning, stacklevel=2,
            )
            audio_source_id = video_id
        if not audio_source_platform and platform:
            audio_source_platform = platform
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        ev = json.dumps(evidence or [])
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO tracks
                  (track_id, artist, title, mbid,
                   audio_source_id, audio_source_platform, video_source_id,
                   platform, genre_slug, filepath, status, error_detail,
                   confidence, evidence, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(track_id) DO UPDATE SET
                  audio_source_id=COALESCE(NULLIF(excluded.audio_source_id,''), tracks.audio_source_id),
                  audio_source_platform=COALESCE(NULLIF(excluded.audio_source_platform,''), tracks.audio_source_platform),
                  video_source_id=COALESCE(NULLIF(excluded.video_source_id,''), tracks.video_source_id),
                  platform=excluded.platform,
                  genre_slug=excluded.genre_slug,
                  filepath=excluded.filepath,
                  status=excluded.status,
                  error_detail=excluded.error_detail,
                  confidence=excluded.confidence,
                  evidence=excluded.evidence,
                  updated_at=excluded.updated_at
                """,
                (
                    tid, artist, title, mbid,
                    audio_source_id, audio_source_platform, video_source_id,
                    platform, genre_slug, filepath, status, error_detail,
                    confidence, ev, now, now,
                ),
            )

    def update_audio_source(
        self,
        track_id_val: str,
        audio_source_id: str,
        platform: str = "youtube",
        title: str = "",
        channel: str = "",
        duration: Optional[int] = None,
    ) -> None:
        """Setea la fuente del MP3 + metadata opcional."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """UPDATE tracks SET
                   audio_source_id=?,
                   audio_source_platform=?,
                   audio_source_title=COALESCE(NULLIF(?, ''), audio_source_title),
                   audio_source_channel=COALESCE(NULLIF(?, ''), audio_source_channel),
                   audio_source_duration=COALESCE(?, audio_source_duration),
                   audio_source_fetched_at=?,
                   updated_at=?
                WHERE track_id=?""",
                (audio_source_id, platform, title, channel, duration,
                 now, now, track_id_val),
            )

    def update_mbid(
        self,
        track_id_val: str,
        mbid: str,
        score: Optional[int] = None,
        album: str = "",
        year: str = "",
    ) -> None:
        """Setea mbid + metadata opcional desde MusicBrainz."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """UPDATE tracks SET
                   mbid=?,
                   mbid_score=COALESCE(?, mbid_score),
                   album=COALESCE(NULLIF(?, ''), album),
                   year=COALESCE(NULLIF(?, ''), year),
                   mb_fetched_at=?,
                   updated_at=?
                WHERE track_id=?""",
                (mbid, score, album, year, now, now, track_id_val),
            )

    # ── Lectura ───────────────────────────────────────────────────────────────

    def get(self, artist: str, title: str) -> Optional[Dict[str, Any]]:
        tid = track_id(artist, title)
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM tracks WHERE track_id=?", (tid,)
            ).fetchone()
        return dict(row) if row else None

    def get_all(self) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def by_status(self, status: str) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        return [dict(r) for r in rows]

    def by_artist(self, artist: str) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks WHERE artist LIKE ? ORDER BY title COLLATE NOCASE",
                (f"%{artist}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def by_genre(self, genre_slug: str) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks WHERE genre_slug=? ORDER BY artist COLLATE NOCASE",
                (genre_slug,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_video_accepted(self, artist: str, title: str, video_filepath: str = "") -> None:
        """Marca video aceptado: guarda path + video_status='video_ok'.
        NO toca curator_status (audio independiente)."""
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """UPDATE tracks SET
                   video_filepath = COALESCE(NULLIF(?, ''), video_filepath),
                   video_status = 'video_ok',
                   updated_at = ?
                WHERE track_id=?""",
                (video_filepath, now, tid),
            )

    def mark_video_rejected(self, artist: str, title: str) -> None:
        """Marca video rechazado: video_status='video_rejected' (terminal).
        NO toca curator_status (audio independiente)."""
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """UPDATE tracks SET
                   video_status = 'video_rejected',
                   updated_at = ?
                WHERE track_id=?""",
                (now, tid),
            )

    def mark_video_unavailable(self, artist: str, title: str) -> None:
        """Marca video no disponible (búsqueda YouTube sin match). Terminal."""
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """UPDATE tracks SET
                   video_status = 'video_unavailable',
                   updated_at = ?
                WHERE track_id=?""",
                (now, tid),
            )

    # ─── Curator methods ─────────────────────────────────────────────────────

    _CURATOR_FLAG_FIELDS = {
        "has_thumbnail", "has_valid_tags", "filename_ok", "genre_folder_ok",
        "is_duplicate_of", "curator_status", "album", "year",
        "filepath", "video_filepath", "genre_slug", "platform", "mbid", "status",
        "mbid_score", "artist", "title",
        "audio_source_id", "audio_source_platform", "audio_source_title",
        "audio_source_channel", "audio_source_duration",
        "video_source_id", "video_source_platform", "video_source_title",
        "video_source_channel", "video_source_duration",
        "metadata_consistent", "has_video_thumbnail", "video_status",
        "bitrate_kbps", "sample_rate", "codec", "channels", "duration_sec",
        "lufs_integrated", "true_peak_db", "dynamic_range",
        "audio_fingerprint", "acoustid_mbid", "audio_quality_score",
    }

    def update_curator_flags(self, track_id_val: str, **flags) -> None:
        """Actualiza columnas de curator. Acepta cualquier campo de _CURATOR_FLAG_FIELDS."""
        if not flags:
            return
        unknown = set(flags) - self._CURATOR_FLAG_FIELDS
        if unknown:
            raise ValueError(f"Campos desconocidos: {unknown}")
        now = datetime.now().isoformat(timespec="seconds")
        sets = ", ".join(f"{k}=?" for k in flags.keys())
        values = list(flags.values()) + [now, now, track_id_val]
        sql = (
            f"UPDATE tracks SET {sets}, curator_checked_at=?, updated_at=? "
            "WHERE track_id=?"
        )
        with self._conn() as con:
            con.execute(sql, values)

    def by_curator_status(self, status: str) -> List[Dict[str, Any]]:
        """Tracks con un curator_status específico."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks WHERE curator_status=? ORDER BY artist COLLATE NOCASE",
                (status,),
            ).fetchall()
        return [dict(r) for r in rows]

    def by_video_status(self, status: str) -> List[Dict[str, Any]]:
        """Tracks con un video_status específico (audio/video separados)."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks WHERE video_status=? ORDER BY artist COLLATE NOCASE",
                (status,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_by_video_status(self) -> Dict[str, int]:
        """Conteo por video_status. NULL → 'unchecked'."""
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT COALESCE(video_status, 'unchecked') AS st, COUNT(*) AS n
                FROM tracks GROUP BY st ORDER BY n DESC
                """
            ).fetchall()
        return {r["st"]: r["n"] for r in rows}

    # Filtros que excluyen estados no operables.
    _SKIP_STATES = "('missing', 'duplicate', 'orphan')"

    def without_thumbnail_with_any_source(self) -> List[Dict[str, Any]]:
        """Tracks sin thumbnail y con AL MENOS UNA fuente (mbid / audio / video).
        Excluye duplicados/missing/orphan (resolver primero con sus fixers)."""
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM tracks
                WHERE (has_thumbnail IS NULL OR has_thumbnail = 0)
                  AND filepath IS NOT NULL AND filepath != ''
                  AND (curator_status IS NULL OR curator_status NOT IN {self._SKIP_STATES})
                  AND (
                    (mbid IS NOT NULL AND mbid != '')
                    OR (audio_source_id IS NOT NULL AND audio_source_id != '')
                    OR (video_source_id IS NOT NULL AND video_source_id != '')
                  )
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def without_audio_source_id(self) -> List[Dict[str, Any]]:
        """Tracks con archivo pero sin audio_source_id (candidatos backfill)."""
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM tracks
                WHERE (audio_source_id IS NULL OR audio_source_id = '')
                  AND filepath IS NOT NULL AND filepath != ''
                  AND (curator_status IS NULL OR curator_status NOT IN {self._SKIP_STATES})
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def without_quality_analyzed(self, force: bool = False) -> List[Dict[str, Any]]:
        """Tracks con archivo que no fueron analizados (o todos si force=True)."""
        query = [
            "SELECT * FROM tracks",
            "WHERE filepath IS NOT NULL AND filepath != ''",
        ]
        if not force:
            query.append("  AND audio_quality_checked_at IS NULL")
        query.append("ORDER BY artist COLLATE NOCASE")
        with self._conn() as con:
            rows = con.execute("\n".join(query)).fetchall()
        return [dict(r) for r in rows]

    def update_quality(self, track_id_val: str, metrics: dict) -> None:
        """Actualiza columnas de análisis de calidad + timestamp."""
        fields = {
            "bitrate_kbps", "sample_rate", "codec", "channels", "duration_sec",
            "lufs_integrated", "true_peak_db", "dynamic_range",
            "audio_fingerprint", "acoustid_mbid", "audio_quality_score",
        }
        updates = [(k, v) for k, v in metrics.items() if k in fields and v is not None]
        if not updates:
            return
        now = datetime.now().isoformat(timespec="seconds")
        sets = ", ".join(f"{k}=?" for k, _ in updates)
        values = [v for _, v in updates] + [now, now, track_id_val]
        sql = (
            f"UPDATE tracks SET {sets}, audio_quality_checked_at=?, updated_at=? "
            "WHERE track_id=?"
        )
        with self._conn() as con:
            con.execute(sql, values)

    def low_quality_candidates(
        self, min_bitrate: int = 192, min_score: int = 60,
    ) -> List[Dict[str, Any]]:
        """Tracks con bitrate o score bajo el umbral (candidatos a re-bajar)."""
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT * FROM tracks
                WHERE filepath IS NOT NULL AND filepath != ''
                  AND (curator_status IS NULL OR curator_status NOT IN ('missing','duplicate','orphan'))
                  AND (
                    (bitrate_kbps IS NOT NULL AND bitrate_kbps > 0 AND bitrate_kbps < ?)
                    OR (audio_quality_score IS NOT NULL AND audio_quality_score < ?)
                  )
                ORDER BY audio_quality_score ASC, bitrate_kbps ASC
                """,
                (min_bitrate, min_score),
            ).fetchall()
        return [dict(r) for r in rows]

    def audio_duplicates_by_fingerprint(self) -> List[List[Dict[str, Any]]]:
        """Grupos de tracks con el mismo audio_fingerprint (>=2 miembros)."""
        from collections import defaultdict
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT * FROM tracks
                WHERE audio_fingerprint IS NOT NULL AND audio_fingerprint != ''
                ORDER BY audio_fingerprint, artist COLLATE NOCASE
                """
            ).fetchall()
        groups = defaultdict(list)
        for r in rows:
            groups[r["audio_fingerprint"]].append(dict(r))
        return [g for g in groups.values() if len(g) > 1]

    def without_mbid(self) -> List[Dict[str, Any]]:
        """Tracks sin MusicBrainz ID (candidatos backfill MB)."""
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM tracks
                WHERE (mbid IS NULL OR mbid = '')
                  AND (curator_status IS NULL OR curator_status NOT IN {self._SKIP_STATES})
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def without_consistent_metadata(self) -> List[Dict[str, Any]]:
        """Tracks con archivo pero metadata inconsistente (fix-metadata)."""
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM tracks
                WHERE (metadata_consistent IS NULL OR metadata_consistent = 0)
                  AND filepath IS NOT NULL AND filepath != ''
                  AND (curator_status IS NULL OR curator_status NOT IN {self._SKIP_STATES})
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def without_video_thumbnail_with_video(self) -> List[Dict[str, Any]]:
        """Tracks con MP4 y video_source_id pero sin covr atom (fix-video-thumbnails)."""
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM tracks
                WHERE video_filepath IS NOT NULL AND video_filepath != ''
                  AND video_source_id IS NOT NULL AND video_source_id != ''
                  AND (has_video_thumbnail IS NULL OR has_video_thumbnail = 0)
                  AND (curator_status IS NULL OR curator_status NOT IN {self._SKIP_STATES})
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def without_valid_tags(self) -> List[Dict[str, Any]]:
        """Tracks con archivo pero tags incompletos (fix-tags candidatos).
        Excluye missing/duplicate/orphan (resolver primero)."""
        with self._conn() as con:
            rows = con.execute(
                f"""
                SELECT * FROM tracks
                WHERE (has_valid_tags IS NULL OR has_valid_tags = 0)
                  AND filepath IS NOT NULL AND filepath != ''
                  AND (curator_status IS NULL OR curator_status NOT IN {self._SKIP_STATES})
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def count_by_curator_status(self) -> Dict[str, int]:
        """Conteo de tracks por curator_status. None -> 'unchecked'."""
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT COALESCE(curator_status, 'unchecked') AS st, COUNT(*) AS n
                FROM tracks GROUP BY st ORDER BY n DESC
                """
            ).fetchall()
        return {r["st"]: r["n"] for r in rows}

    def insert_orphan(
        self,
        artist: str,
        title: str,
        filepath: str,
        genre_slug: str = "",
        album: str = "",
        year: str = "",
        has_thumbnail: int = 0,
    ) -> str:
        """Inserta un track marcado como orphan (existía en disco pero no en BD)."""
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO tracks
                  (track_id, artist, title, genre_slug, filepath, status,
                   album, year, has_thumbnail, curator_status,
                   curator_checked_at, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(track_id) DO UPDATE SET
                  filepath=excluded.filepath,
                  curator_status='orphan',
                  updated_at=excluded.updated_at
                """,
                (tid, artist, title, genre_slug, filepath, "existing",
                 album, year, has_thumbnail, "orphan", now, now, now),
            )
        return tid

    def insert_video_orphan(
        self,
        artist: str,
        title: str,
        video_filepath: str,
        genre_slug: str = "",
    ) -> str:
        """Inserta un MP4 huérfano (video en disco sin track en BD).
        filepath queda vacío (no hay audio)."""
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO tracks
                  (track_id, artist, title, genre_slug, filepath,
                   video_filepath, status, curator_status, video_status,
                   curator_checked_at, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(track_id) DO UPDATE SET
                  video_filepath=excluded.video_filepath,
                  video_status='video_ok',
                  updated_at=excluded.updated_at
                """,
                (tid, artist, title, genre_slug, "",
                 video_filepath, "existing", "orphan", "video_ok",
                 now, now, now),
            )
        return tid

    def video_stale(self) -> List[Dict[str, Any]]:
        """Tracks con video_filepath seteado pero archivo no existe en disco."""
        import os as _os
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT * FROM tracks
                WHERE video_filepath IS NOT NULL AND video_filepath != ''
                ORDER BY artist COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows if not _os.path.isfile(r["video_filepath"])]

    def reset_legacy_albums(self, slugs: list) -> int:
        """Resetea BD.album a '' donde coincide con algún slug (legacy rule).
        Retorna cantidad de filas afectadas."""
        if not slugs:
            return 0
        placeholders = ",".join("?" * len(slugs))
        with self._conn() as con:
            cur = con.execute(
                f"UPDATE tracks SET album = '' WHERE album IN ({placeholders})",
                list(slugs),
            )
            return cur.rowcount

    def delete_track(self, track_id_val: str) -> None:
        """Borra una fila (para reconciliación de fantasmas confirmadas)."""
        with self._conn() as con:
            con.execute("DELETE FROM tracks WHERE track_id=?", (track_id_val,))

    def artist_genre_stats(self, artist: str) -> Dict[str, int]:
        """Cuenta géneros ya clasificados para este artista (Capa C2 — artist memory).
        Excluye slug vacío. Retorna {slug: count}."""
        if not artist:
            return {}
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT genre_slug AS slug, COUNT(*) AS n
                FROM tracks
                WHERE artist = ? COLLATE NOCASE
                  AND genre_slug IS NOT NULL AND genre_slug != ''
                GROUP BY genre_slug
                """,
                (artist,),
            ).fetchall()
        return {r["slug"]: r["n"] for r in rows}

    def classifier_summary(self) -> Dict[str, Any]:
        """Estadísticas para Capa D2 (mala-pata classifier-stats)."""
        with self._conn() as con:
            by_genre = con.execute(
                """
                SELECT COALESCE(NULLIF(genre_slug, ''), '(sin género)') AS slug,
                       COUNT(*) AS n,
                       AVG(COALESCE(confidence, 0)) AS avg_conf
                FROM tracks
                GROUP BY slug
                ORDER BY n DESC
                """
            ).fetchall()
            low_conf = con.execute(
                """
                SELECT artist, title, genre_slug, confidence
                FROM tracks
                WHERE confidence > 0 AND confidence < 0.5
                ORDER BY confidence ASC
                LIMIT 30
                """
            ).fetchall()
            total = con.execute("SELECT COUNT(*) AS n FROM tracks").fetchone()["n"]
        return {
            "total": total,
            "by_genre": [dict(r) for r in by_genre],
            "low_conf": [dict(r) for r in low_conf],
        }
