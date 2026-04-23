# mpc/curator/replace.py
# -*- coding: utf-8 -*-
"""
Replace: re-descarga audio/video/thumbnail de un track existente
preservando metadata de BD.

Tres operaciones:
  - replace_audio   : MP3 desde YouTube, preserva tags BD (artist/title/album/genre/year)
  - replace_video   : MP4 desde YouTube, aplica tags QuickTime desde BD
  - replace_thumbnail: solo baja y embebe JPG (APIC en MP3, covr en MP4)

Búsqueda de track por fuzzy match sobre `artist + " " + title` de BD.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mpc.library.repository import TrackRepository
from mpc.utils.text import sanitize_filename_component, canonical_filename


# ────────────────────────────────────────────────────────────────
# Fuzzy search
# ────────────────────────────────────────────────────────────────

def _score(query: str, candidate: str) -> int:
    """Score 0-100 usando SequenceMatcher + token_set bonus."""
    q = query.lower().strip()
    c = candidate.lower().strip()
    if not q or not c:
        return 0
    base = SequenceMatcher(None, q, c).ratio() * 100
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if q_tokens and c_tokens:
        overlap = len(q_tokens & c_tokens) / len(q_tokens)
        base = base * 0.6 + overlap * 100 * 0.4
    return int(base)


def fuzzy_find(
    repo: TrackRepository, query: str, limit: int = 5, min_score: int = 40
) -> List[Tuple[int, Dict]]:
    """Top N candidatos ordenados por score desc."""
    all_tracks = repo.get_all()
    scored = []
    for t in all_tracks:
        fp = t.get("filepath") or ""
        if not fp:
            continue
        label = f"{t.get('artist', '')} {t.get('title', '')}"
        s = _score(query, label)
        if s >= min_score:
            scored.append((s, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def interactive_pick(
    candidates: List[Tuple[int, Dict]], auto_if_clear: bool = True
) -> Optional[Dict]:
    """Muestra candidatos y pide selección. None si cancela."""
    if not candidates:
        print("❌ Sin matches")
        return None

    if (
        auto_if_clear
        and len(candidates) >= 1
        and candidates[0][0] >= 95
        and (len(candidates) == 1 or candidates[1][0] < 70)
    ):
        s, t = candidates[0]
        print(f"✅ Match claro: {t['artist']} - {t['title']} (score {s})")
        return t

    for i, (s, t) in enumerate(candidates, 1):
        genre = t.get("genre_slug") or "?"
        album = t.get("album") or "—"
        print(f"  [{i}] {t['artist']} - {t['title']}  "
              f"[{genre}] album={album!r}  (score {s})")
    print(f"  [{len(candidates) + 1}] Cancelar")

    while True:
        try:
            choice = input("Elegí: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not choice.isdigit():
            continue
        n = int(choice)
        if n == len(candidates) + 1:
            return None
        if 1 <= n <= len(candidates):
            return candidates[n - 1][1]


# ────────────────────────────────────────────────────────────────
# Replace: audio (MP3)
# ────────────────────────────────────────────────────────────────

_YTDLP_AUDIO_BASE = ["-x", "--audio-format", "mp3", "--audio-quality", "0", "-o"]


def replace_audio(repo: TrackRepository, track: Dict, youtube_id: str) -> bool:
    """Re-descarga MP3 desde YouTube y aplica tags desde BD."""
    from mpc.acquisition.steps.tagger import MetadataTagger
    from mpc.curator.fixers.thumbnails import fetch_from_youtube

    if not shutil.which("yt-dlp"):
        print("❌ yt-dlp no está en PATH")
        return False

    old_fp = track.get("filepath") or ""
    if not old_fp:
        print("❌ Track sin filepath en BD")
        return False

    artist = track["artist"]
    title = track["title"]
    genre_slug = track.get("genre_slug") or ""
    album = track.get("album") or ""
    year = track.get("year") or ""

    target_dir = str(Path(old_fp).parent)
    filename = canonical_filename(artist, title, ".mp3")
    new_fp = os.path.join(target_dir, filename)

    url = f"https://www.youtube.com/watch?v={youtube_id}"
    print(f"→ Descargando MP3 de {youtube_id}...")
    cmd = ["yt-dlp"] + _YTDLP_AUDIO_BASE + [new_fp, url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(new_fp):
        print(f"❌ yt-dlp falló: {(r.stderr or '')[:200]}")
        return False

    # Thumbnail
    thumb_path = ""
    jpg = fetch_from_youtube(youtube_id)
    if jpg:
        import tempfile
        tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tf.write(jpg)
        tf.close()
        thumb_path = tf.name

    # Aplicar tags con ffmpeg (MetadataTagger resuelve album vía resolver si vacío)
    print("→ Aplicando tags desde BD...")
    tagger = MetadataTagger()
    ok = tagger.tag(
        new_fp,
        sanitize_filename_component(artist),
        sanitize_filename_component(title),
        genre_slug,
        thumb_path or None,
    )

    # Si BD tiene album/year explícitos, forzarlos con mutagen (sobrescribe resolver)
    if album or year:
        _force_id3(new_fp, album=album, year=year)

    if thumb_path and os.path.exists(thumb_path):
        os.unlink(thumb_path)

    # Actualizar BD
    flags = {
        "audio_source_id": youtube_id,
        "filepath": new_fp,
        "has_thumbnail": 1 if jpg else track.get("has_thumbnail", 0),
        "has_valid_tags": 1,
        "filename_ok": 1,
        "metadata_consistent": 1,
    }
    repo.update_curator_flags(track["track_id"], **flags)
    print(f"✅ MP3 reemplazado: {new_fp}")
    return ok


def _force_id3(path: str, album: str = "", year: str = "") -> None:
    """Sobrescribe TALB/TDRC con valores de BD si están seteados."""
    try:
        from mutagen.id3 import ID3, TALB, TDRC, ID3NoHeaderError
    except ImportError:
        return
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    if album:
        tags.delall("TALB")
        tags.add(TALB(encoding=3, text=album))
    if year:
        tags.delall("TDRC")
        tags.add(TDRC(encoding=3, text=year))
    tags.save(path, v2_version=3)


# ────────────────────────────────────────────────────────────────
# Replace: video (MP4)
# ────────────────────────────────────────────────────────────────

_VIDEO_FORMAT_STRATEGIES = [
    "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/best[vcodec^=avc1][ext=mp4]",
    "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]",
    "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]",
    "bestvideo+bestaudio/best",
]


def replace_video(repo: TrackRepository, track: Dict, youtube_id: str) -> bool:
    """Re-descarga MP4 y aplica tags QuickTime desde BD."""
    from mpc.curator.fixers._mp4_utils import write_mp4_tags
    from mpc.curator.fixers.thumbnails import fetch_from_youtube
    from mpc.catalog.genres import genre_name as _gname

    if not shutil.which("yt-dlp"):
        print("❌ yt-dlp no está en PATH")
        return False

    artist = track["artist"]
    title = track["title"]
    genre_slug = track.get("genre_slug") or ""
    album = track.get("album") or ""
    year = track.get("year") or ""

    # Path: junto al MP3 o en la carpeta del genre_slug
    audio_fp = track.get("filepath") or ""
    old_video_fp = track.get("video_filepath") or ""
    if old_video_fp:
        target_dir = str(Path(old_video_fp).parent)
    elif audio_fp:
        target_dir = str(Path(audio_fp).parent)
    else:
        print("❌ No hay filepath ni video_filepath de referencia")
        return False

    filename = canonical_filename(artist, title, ".mp4")
    new_fp = os.path.join(target_dir, filename)

    # Borrar anterior si existe y tiene otro nombre
    if old_video_fp and old_video_fp != new_fp and os.path.isfile(old_video_fp):
        try:
            os.unlink(old_video_fp)
        except OSError:
            pass

    url = f"https://www.youtube.com/watch?v={youtube_id}"
    print(f"→ Descargando MP4 de {youtube_id}...")

    success = False
    for fmt in _VIDEO_FORMAT_STRATEGIES:
        cmd = [
            "yt-dlp", "-f", fmt, "--merge-output-format", "mp4",
            "-o", new_fp, url,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and os.path.exists(new_fp):
            success = True
            break
        if "Requested format is not available" not in (r.stderr or ""):
            break
    if not success:
        print("❌ yt-dlp falló todas las estrategias")
        return False

    # Tags MP4 desde BD
    print("→ Aplicando tags QuickTime desde BD...")
    try:
        write_mp4_tags(
            new_fp,
            artist=sanitize_filename_component(artist),
            title=sanitize_filename_component(title),
            album=album or None,
            genre=_gname(genre_slug) or None,
            year=year or None,
            overwrite=True,
        )
    except Exception as e:
        print(f"⚠️ tags MP4 falló: {e}")

    # covr desde YouTube thumbnail
    try:
        from mutagen.mp4 import MP4, MP4Cover
        jpg = fetch_from_youtube(youtube_id)
        if jpg:
            mp4 = MP4(new_fp)
            mp4["covr"] = [MP4Cover(jpg, imageformat=MP4Cover.FORMAT_JPEG)]
            mp4.save()
    except Exception as e:
        print(f"⚠️ covr embed falló: {e}")

    repo.update_curator_flags(
        track["track_id"],
        video_source_id=youtube_id,
        video_filepath=new_fp,
        has_video_thumbnail=1,
        video_status="video_ok",
    )
    print(f"✅ MP4 reemplazado: {new_fp}")
    return True


# ────────────────────────────────────────────────────────────────
# Replace: thumbnail (solo arte, preserva tags)
# ────────────────────────────────────────────────────────────────

def replace_thumbnail(
    repo: TrackRepository, track: Dict, youtube_id: str
) -> bool:
    """Baja thumbnail de YouTube y lo embebe en MP3 (APIC) y MP4 (covr) si existe."""
    from mpc.curator.fixers.thumbnails import fetch_from_youtube, embed_thumbnail

    jpg = fetch_from_youtube(youtube_id)
    if not jpg:
        print(f"❌ YouTube {youtube_id} sin thumbnail disponible")
        return False

    ok_any = False
    audio_fp = track.get("filepath") or ""
    if audio_fp and os.path.isfile(audio_fp):
        try:
            embed_thumbnail(audio_fp, jpg)
            print(f"✅ APIC embebido en MP3 ({len(jpg)} bytes)")
            ok_any = True
        except Exception as e:
            print(f"❌ MP3 embed falló: {e}")

    video_fp = track.get("video_filepath") or ""
    if video_fp and os.path.isfile(video_fp):
        try:
            from mutagen.mp4 import MP4, MP4Cover
            mp4 = MP4(video_fp)
            mp4["covr"] = [MP4Cover(jpg, imageformat=MP4Cover.FORMAT_JPEG)]
            mp4.save()
            print(f"✅ covr embebido en MP4 ({len(jpg)} bytes)")
            ok_any = True
        except Exception as e:
            print(f"❌ MP4 embed falló: {e}")

    if ok_any:
        flags = {"has_thumbnail": 1}
        if video_fp:
            flags["has_video_thumbnail"] = 1
        repo.update_curator_flags(track["track_id"], **flags)
    return ok_any
