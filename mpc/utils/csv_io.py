# mpc/utils/csv_io.py
# -*- coding: utf-8 -*-
"""
Lectura y escritura de CSV compartida entre create y pipeline.
Schema: artist, title, query_override, source, [genre]
"""

import csv
import os
from typing import List, Dict, Optional

FIELDNAMES_BASE = ["artist", "title", "query_override", "source"]
FIELDNAMES_GENRE = ["artist", "title", "query_override", "source", "genre"]


def read_csv(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows: List[Dict], path: str, genre: Optional[str] = None):
    """
    Escribe rows al CSV.
    Si genre no es None, añade columna 'genre' con ese valor para todas las filas.
    Si las filas ya traen 'genre', lo usa.
    """
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

    # Decidir fieldnames
    has_genre_col = genre is not None or any(r.get("genre") for r in rows)
    fieldnames = FIELDNAMES_GENRE if has_genre_col else FIELDNAMES_BASE

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row_data = {
                "artist": r.get("artist", ""),
                "title": r.get("title", ""),
                "query_override": r.get("query_override", ""),
                "source": r.get("source", ""),
            }
            if has_genre_col:
                row_data["genre"] = genre if genre is not None else r.get("genre", "")
            w.writerow(row_data)


def append_csv(rows: List[Dict], path: str, genre: Optional[str] = None):
    """
    Añade filas a un CSV existente. Si no existe, lo crea.
    Respeta el schema del archivo existente (con o sin columna genre).
    """
    if not os.path.exists(path):
        write_csv(rows, path, genre)
        return

    existing = read_csv(path)
    # detectar si ya tiene columna genre
    has_genre = any("genre" in r for r in existing) or genre is not None or any(r.get("genre") for r in rows)
    fieldnames = FIELDNAMES_GENRE if has_genre else FIELDNAMES_BASE

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        for r in rows:
            row_data = {
                "artist": r.get("artist", ""),
                "title": r.get("title", ""),
                "query_override": r.get("query_override", ""),
                "source": r.get("source", ""),
            }
            if has_genre:
                row_data["genre"] = genre if genre is not None else r.get("genre", "")
            w.writerow(row_data)
