# mpc/curator/fixers/backfill.py
# -*- coding: utf-8 -*-
"""
Backfillers: rellenan datos faltantes sin descargar contenido.

- AudioSourceBackfiller: busca en YouTube los IDs de audio_source_id faltantes.
- MbidBackfiller: consulta MusicBrainz para rellenar mbid faltantes.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Optional

from mpc.config import get_config
from mpc.library.repository import TrackRepository


def _is_audio_oriented(title: str, channel: str) -> bool:
    """Heurística: preferir canales '- Topic', 'VEVO', 'Records' y títulos con 'audio'."""
    t = (title or "").lower()
    c = (channel or "").lower()
    if "- topic" in c or c.endswith("- topic"):
        return True
    if "vevo" in c or "records" in c or "music" in c:
        return True
    if "official audio" in t or "(audio)" in t or "[audio]" in t:
        return True
    # evita claramente visuals
    bad = ("live", "concert", "concierto", "en vivo", "lyric", "lyrics", "reaction")
    if any(b in t for b in bad):
        return False
    return True


class AudioSourceBackfiller:
    def __init__(self, repo: TrackRepository):
        self.repo = repo

    def run(self, dry_run: bool = False, limit: Optional[int] = None,
            sleep_sec: float = 2.0) -> dict:
        cfg = get_config()
        ytdlp = getattr(cfg, "ytdlp_bin", "yt-dlp")

        tracks = self.repo.without_audio_source_id()
        if limit:
            tracks = tracks[:limit]

        found = 0
        failed = 0

        for i, t in enumerate(tracks, 1):
            artist = t["artist"]
            title = t["title"]
            label = f"[{i}/{len(tracks)}] {artist} - {title}"

            if dry_run:
                print(f"{label} [DRY-RUN] buscaría en YouTube")
                continue

            query = f"{artist} {title} audio"
            try:
                cmd = [
                    ytdlp, "--default-search", "ytsearch5",
                    "--dump-json", "--no-download",
                    "--playlist-end", "5",
                    query,
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode != 0:
                    print(f"{label} ❌ yt-dlp falló")
                    failed += 1
                    continue
                candidates = []
                for line in r.stdout.strip().split("\n"):
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    vid = data.get("id", "")
                    vtitle = data.get("title", "")
                    channel = data.get("channel", "") or data.get("uploader", "")
                    duration = data.get("duration") or 0
                    if not vid:
                        continue
                    if duration and (duration < 60 or duration > 600):
                        continue
                    if _is_audio_oriented(vtitle, channel):
                        candidates.append((vid, vtitle, channel, duration))
                if not candidates:
                    print(f"{label} ⚠️  sin matches audio-oriented")
                    failed += 1
                else:
                    vid, vtitle, channel, duration = candidates[0]
                    self.repo.update_audio_source(
                        t["track_id"], vid,
                        platform="youtube",
                        title=vtitle,
                        channel=channel,
                        duration=int(duration) if duration else None,
                    )
                    print(f"{label} ✅ {vid} [{int(duration or 0)}s] {channel[:30]}")
                    found += 1
            except Exception as e:
                print(f"{label} ❌ {type(e).__name__}: {e}")
                failed += 1

            time.sleep(sleep_sec)

        return {"total": len(tracks), "found": found, "failed": failed}


class MbidBackfiller:
    def __init__(self, repo: TrackRepository):
        self.repo = repo

    def run(self, dry_run: bool = False, limit: Optional[int] = None,
            min_score: int = 90) -> dict:
        try:
            from mpc.sources.musicbrainz import mb_search_recordings
        except ImportError:
            print("❌ MusicBrainz no disponible")
            return {"total": 0, "found": 0, "failed": 0}

        tracks = self.repo.without_mbid()
        if limit:
            tracks = tracks[:limit]

        found = 0
        failed = 0

        for i, t in enumerate(tracks, 1):
            artist = t["artist"]
            title = t["title"]
            label = f"[{i}/{len(tracks)}] {artist} - {title}"

            if dry_run:
                print(f"{label} [DRY-RUN] consultaría MB")
                continue

            try:
                from mpc.sources.musicbrainz import mb_get, _lucene_escape
                q = f'artist:"{_lucene_escape(artist)}" AND recording:"{_lucene_escape(title)}"'
                data = mb_get("recording", {"query": q, "limit": 3})
                recs = data.get("recordings", [])
                if not recs:
                    print(f"{label} ⚠️  sin match en MB")
                    failed += 1
                    continue
                top = recs[0]
                score = int(top.get("score", 0) or 0)
                if score < min_score:
                    print(f"{label} ⚠️  score bajo ({score})")
                    failed += 1
                    continue
                mbid = top.get("id", "")
                if not mbid:
                    failed += 1
                    continue
                # Extraer album y year del primer release
                album = ""
                year = ""
                releases = top.get("releases", [])
                if releases:
                    album = releases[0].get("title", "") or ""
                    date = releases[0].get("date", "") or ""
                    year = date.split("-")[0] if date else ""
                self.repo.update_mbid(
                    t["track_id"], mbid,
                    score=score, album=album, year=year,
                )
                extra = f" [{album} / {year}]" if album or year else ""
                print(f"{label} ✅ {mbid} (score={score}){extra}")
                found += 1
            except Exception as e:
                print(f"{label} ❌ {type(e).__name__}: {e}")
                failed += 1

        return {"total": len(tracks), "found": found, "failed": failed}
