# mpc/curator/fixers/_mp4_utils.py
# -*- coding: utf-8 -*-
"""
Helpers compartidos para operaciones sobre archivos MP4 (QuickTime atoms).
Usado por MetadataFixer, TagFixer, etc.
"""

from __future__ import annotations

from typing import Optional

try:
    from mutagen.mp4 import MP4
except ImportError:
    MP4 = None


def write_mp4_tags(
    path: str,
    artist: Optional[str] = None,
    title: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    overwrite: bool = True,
) -> bool:
    """
    Escribe tags QuickTime en un MP4. Si overwrite=False, solo llena vacíos.

    Mapeo atoms:
      ©ART → artist
      ©nam → title
      ©alb → album  (regla: genre_slug)
      ©gen → genre  (regla: genre_slug)
      ©day → year

    Retorna True si algo se escribió, False si no cambió nada o falló.
    """
    if MP4 is None:
        return False

    try:
        mp4 = MP4(path)
    except Exception:
        return False

    changed = False

    def _set(key: str, value: Optional[str]) -> None:
        nonlocal changed
        if value is None:
            return
        existing = mp4.get(key)
        has_val = bool(existing and str(existing[0]).strip()) if existing else False
        if overwrite or not has_val:
            if not existing or str(existing[0]) != str(value):
                mp4[key] = [value]
                changed = True

    _set("\xa9ART", artist)
    _set("\xa9nam", title)
    _set("\xa9alb", album)
    _set("\xa9gen", genre)
    _set("\xa9day", year)

    if changed:
        try:
            mp4.save()
            return True
        except Exception:
            return False
    return False


def read_mp4_tags(path: str) -> dict:
    """Lee tags QuickTime de un MP4. Devuelve dict con keys canónicas."""
    if MP4 is None:
        return {}
    try:
        mp4 = MP4(path)
    except Exception:
        return {}
    out = {}
    for key, dict_key in [
        ("\xa9ART", "artist"),
        ("\xa9nam", "title"),
        ("\xa9alb", "album"),
        ("\xa9gen", "genre"),
        ("\xa9day", "year"),
    ]:
        val = mp4.get(key)
        if val:
            out[dict_key] = str(val[0]).strip()
    # covr indicates thumbnail presence
    out["has_covr"] = bool(mp4.get("covr"))
    return out
