#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import re
import unicodedata
import argparse
from typing import List, Dict, Set
from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

# ---------- Title Case "bonito" ----------
LOWER_EXCEPTIONS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "u", "en", "con", "por", "para",
    "a", "al", "un", "una", "uno", "unos", "unas", "the", "of", "and", "feat.", "ft."
}


def _normalize_spaces(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", " ", s.strip())
    return s


def title_case_keep_caps(text: str) -> str:
    text = _normalize_spaces(text)
    if not text:
        return text
    out = []
    for i, w in enumerate(text.split(" ")):
        if not w:
            out.append(w)
            continue
        if w.isupper() and len(w) > 1:  # siglas (FANIA, NG, DJ)
            out.append(w)
            continue
        base = w.lower()
        out.append(base if (i > 0 and base in LOWER_EXCEPTIONS)
                   else base[:1].upper() + base[1:])
    return " ".join(out)


def simp(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = "".join(c for c in unicodedata.normalize(
        "NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def key_pair(artist: str, title: str) -> str:
    return f"{simp(artist)}|{simp(title)}"

# ---------- Spotify ----------


def get_spotify_client():
    import os
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    cid = os.getenv("SPOTIFY_CLIENT_ID")
    secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect = os.getenv("SPOTIFY_REDIRECT_URI",
                         "https://localhost:8080/callback")

    cache_path = os.path.join(PROJECT_DIR, "cache/spotify_token_cache")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    scope = "playlist-read-private playlist-read-collaborative"
    auth = SpotifyOAuth(
        client_id=cid,
        client_secret=secret,
        redirect_uri=redirect,      # debe coincidir EXACTO con el Dashboard
        scope=scope,
        cache_path=cache_path,
        open_browser=True           # abre navegador y captura el callback
    )
    return spotipy.Spotify(auth_manager=auth)


def parse_playlist_id(s: str) -> str:
    # acepta ID crudo, URL web, o spotify:playlist:ID
    if ":" in s and s.startswith("spotify:playlist:"):
        return s.split(":")[-1]
    if "open.spotify.com/playlist/" in s:
        # .../playlist/{id}?si=...
        part = s.split("open.spotify.com/playlist/")[1]
        return part.split("?")[0].split("/")[0]
    return s  # asume que ya es un ID


def fetch_playlist_tracks(sp, playlist_id: str, limit_count: int = None) -> List[Dict]:
    items: List[Dict] = []
    fields = "items(track(name,artists(name),album(name))),next"
    results = sp.playlist_items(playlist_id, fields=fields, additional_types=[
                                "track"], limit=100, offset=0)
    while True:
        for it in results.get("items", []):
            tr = it.get("track")
            if not tr:
                continue
            title = tr.get("name") or ""
            artists = tr.get("artists") or []
            artist = artists[0]["name"] if artists else ""
            album = (tr.get("album") or {}).get("name", "") or ""
            items.append({"artist": artist, "title": title, "album": album})
            if limit_count and len(items) >= limit_count:
                return items
        nxt = results.get("next")
        if not nxt:
            break
        results = sp.next(results)
    return items


def write_csv(rows: List[Dict], out_path: str, genre: str = None):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["artist", "title", "query_override", "source", "genre"])
        w.writeheader()
        for r in rows:
            artist_fmt = title_case_keep_caps(r["artist"])
            title_fmt = title_case_keep_caps(r["title"])
            album = r.get("album") or ""
            qov = f'{artist_fmt} {title_fmt} {album}'.strip()
            w.writerow({
                "artist": artist_fmt,
                "title": title_fmt,
                "query_override": qov,
                "source": "spotify",
                "genre": genre or ""
            })


def main():
    ap = argparse.ArgumentParser(
        description="Exporta una playlist de Spotify a canciones.csv para el pipeline.")
    ap.add_argument("playlist", help="URL o ID de la playlist de Spotify")
    ap.add_argument("--out", default=os.path.join(PROJECT_DIR, "canciones.csv"),
                    help="CSV de salida (default: canciones.csv)")
    ap.add_argument("--count", type=int, help="Limitar a N canciones")
    ap.add_argument("--genre", help="Género a asignar a todas las canciones (ej: salsa, house, balada)")
    args = ap.parse_args()

    sp = get_spotify_client()
    pid = parse_playlist_id(args.playlist)

    print("🎧 Leyendo playlist…")
    tracks = fetch_playlist_tracks(sp, pid, limit_count=args.count)

    # dedupe por (artist,title)
    seen: Set[str] = set()
    rows: List[Dict] = []
    for t in tracks:
        k = key_pair(t["artist"], t["title"])
        if k in seen:
            continue
        seen.add(k)
        rows.append(t)

    write_csv(rows, args.out, genre=args.genre)
    if args.genre:
        print(f"✅ CSV generado: {args.out}  ({len(rows)} temas) - Género: {args.genre}")
    else:
        print(f"✅ CSV generado: {args.out}  ({len(rows)} temas)")
    print("   Ejecuta ahora: come-candela")


if __name__ == "__main__":
    main()
