# mpc/library/repository.py
# -*- coding: utf-8 -*-
"""
TrackRepository: fuente de verdad de la colección.

Reemplaza ManifestService (CSV) con SQLite para soportar:
  - Consultas reales (by_artist, by_genre, failed)
  - Resume: saber exactamente qué descargué y en qué estado
  - Historial de errores por track
  - Almacenamiento de metadatos de discovery (confidence, evidence, intent)

Compatibilidad: importa manifest.csv legado al inicializar si existe y la
tabla está vacía.
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
    video_id     TEXT,
    platform     TEXT,
    genre_slug   TEXT,
    filepath     TEXT,
    status       TEXT NOT NULL,
    error_detail TEXT,
    confidence   REAL,
    evidence     TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artist    ON tracks(artist COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_genre     ON tracks(genre_slug);
CREATE INDEX IF NOT EXISTS idx_status    ON tracks(status);
"""


class TrackRepository:
    """
    Repositorio SQLite de tracks descargados / intentados.

    Thread-safe: cada llamada abre una conexión corta (WAL mode).
    """

    def __init__(self, db_path: str, legacy_csv: Optional[str] = None):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()
        if legacy_csv:
            self._import_legacy_csv(legacy_csv)

    # ── Inicialización ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as con:
            con.executescript(_SCHEMA)

    def _import_legacy_csv(self, csv_path: str) -> None:
        """Importa manifest.csv legado si la tabla está vacía."""
        if not os.path.exists(csv_path):
            return
        with self._conn() as con:
            count = con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            if count > 0:
                return
        try:
            import csv as _csv
            with open(csv_path, newline="", encoding="utf-8") as f:
                rows = list(_csv.DictReader(f))
            imported = 0
            for row in rows:
                artist = (row.get("artist") or "").strip()
                title = (row.get("title") or "").strip()
                if not artist or not title:
                    continue
                self.record(
                    artist=artist,
                    title=title,
                    video_id=(row.get("video_id") or "").strip(),
                    platform="youtube",
                    genre_slug=(row.get("genre_slug") or "").strip(),
                    filepath=(row.get("filepath") or "").strip(),
                    status=(row.get("status") or "downloaded").strip(),
                )
                imported += 1
            logger.info("repository: importados %d tracks desde %s", imported, csv_path)
        except Exception as e:
            logger.warning("repository: error importando CSV legado: %s", e)

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
        video_id: str = "",
        platform: str = "",
        genre_slug: str = "",
        filepath: str = "",
        status: str = "downloaded",
        error_detail: str = "",
        confidence: float = 0.0,
        evidence: Optional[List[str]] = None,
        mbid: Optional[str] = None,
    ) -> None:
        """Inserta o actualiza un track. UPSERT por track_id."""
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        ev = json.dumps(evidence or [])
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO tracks
                  (track_id, artist, title, mbid, video_id, platform,
                   genre_slug, filepath, status, error_detail,
                   confidence, evidence, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(track_id) DO UPDATE SET
                  video_id=excluded.video_id,
                  platform=excluded.platform,
                  genre_slug=excluded.genre_slug,
                  filepath=excluded.filepath,
                  status=excluded.status,
                  error_detail=excluded.error_detail,
                  confidence=excluded.confidence,
                  evidence=excluded.evidence,
                  updated_at=excluded.updated_at
                """,
                (tid, artist, title, mbid, video_id, platform,
                 genre_slug, filepath, status, error_detail,
                 confidence, ev, now, now),
            )

    def mark_failed(self, artist: str, title: str, error_detail: str = "") -> None:
        tid = track_id(artist, title)
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as con:
            con.execute(
                "UPDATE tracks SET status='failed', error_detail=?, updated_at=? WHERE track_id=?",
                (error_detail, now, tid),
            )

    # ── Lectura ───────────────────────────────────────────────────────────────

    def contains(self, artist: str, title: str) -> bool:
        """True si el track ya está registrado (cualquier estado)."""
        tid = track_id(artist, title)
        with self._conn() as con:
            row = con.execute(
                "SELECT 1 FROM tracks WHERE track_id=?", (tid,)
            ).fetchone()
        return row is not None

    def get(self, artist: str, title: str) -> Optional[Dict[str, Any]]:
        tid = track_id(artist, title)
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM tracks WHERE track_id=?", (tid,)
            ).fetchone()
        return dict(row) if row else None

    def get_all(self) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM tracks ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def by_status(self, status: str) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM tracks WHERE status=? ORDER BY updated_at DESC", (status,)
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
