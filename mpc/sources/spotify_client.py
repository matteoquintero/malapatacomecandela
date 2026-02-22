# mpc/sources/spotify_client.py
# -*- coding: utf-8 -*-
"""
Cliente Spotify compartido. Usado por create --spotify y por el fallback
de búsqueda de artista en request_to_csv.
"""

import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger("mpc.sources.spotify")


def get_spotify_client_credentials(client_id: str, client_secret: str):
    """
    Cliente con Client Credentials (sin user auth).
    Sirve para búsquedas de artista/track sin acceso a playlists privadas.
    """
    if not client_id or not client_secret:
        return None
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        from spotipy.cache_handler import MemoryCacheHandler
        auth = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
            cache_handler=MemoryCacheHandler(),
        )
        sp = spotipy.Spotify(client_credentials_manager=auth)
        logger.debug("Spotify (credentials) client OK")
        return sp
    except ImportError:
        logger.warning("spotipy no instalado. pip install spotipy")
        return None
    except Exception as e:
        logger.warning("Error iniciando Spotify (credentials): %s", e)
        return None


def get_spotify_client_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    cache_path: str,
) -> Optional[object]:
    """
    Cliente con OAuth (user auth). Necesario para playlists privadas.
    Abre navegador en el primer uso.
    """
    if not client_id or not client_secret:
        return None
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        os.makedirs(os.path.dirname(cache_path) if os.path.dirname(cache_path) else ".", exist_ok=True)
        scope = "playlist-read-private playlist-read-collaborative"
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=cache_path,
            open_browser=True,
        )
        sp = spotipy.Spotify(auth_manager=auth)
        logger.debug("Spotify (OAuth) client OK")
        return sp
    except ImportError:
        logger.warning("spotipy no instalado. pip install spotipy")
        return None
    except Exception as e:
        logger.warning("Error iniciando Spotify (OAuth): %s", e)
        return None


# ── Parsers de URL ─────────────────────────────────────────────────────────────

def parse_playlist_id(s: str) -> str:
    if s.startswith("spotify:playlist:"):
        return s.split(":")[-1]
    if "open.spotify.com/playlist/" in s:
        part = s.split("open.spotify.com/playlist/")[1]
        return part.split("?")[0].split("/")[0]
    return s


def parse_album_id(s: str) -> str:
    if s.startswith("spotify:album:"):
        return s.split(":")[-1]
    if "open.spotify.com/album/" in s:
        part = s.split("open.spotify.com/album/")[1]
        return part.split("?")[0].split("/")[0]
    return s


def detect_source_type(url: str) -> str:
    """Detecta automáticamente si la URL es playlist o album."""
    if "album" in url or ":album:" in url:
        return "album"
    return "playlist"


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_playlist_tracks(sp, playlist_id: str, limit_count: Optional[int] = None) -> List[Dict]:
    items: List[Dict] = []
    fields = "items(track(name,artists(name),album(name))),next"
    results = sp.playlist_items(
        playlist_id, fields=fields, additional_types=["track"], limit=100, offset=0
    )
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


def fetch_album_tracks(sp, album_id: str, limit_count: Optional[int] = None) -> List[Dict]:
    items: List[Dict] = []
    album_info = sp.album(album_id)
    album_name = album_info.get("name", "")
    results = sp.album_tracks(album_id, limit=50, offset=0)
    while True:
        for tr in results.get("items", []):
            if not tr:
                continue
            title = tr.get("name") or ""
            artists = tr.get("artists") or []
            artist = artists[0]["name"] if artists else ""
            items.append({"artist": artist, "title": title, "album": album_name})
            if limit_count and len(items) >= limit_count:
                return items
        nxt = results.get("next")
        if not nxt:
            break
        results = sp.next(results)
    return items


def search_artist_tracks(sp, artist: str, count: int, genre: Optional[str] = None) -> List[Dict]:
    """
    Busca tracks de un artista usando la API de Spotify.
    Usado como fallback cuando MB/Discogs no encuentran nada.
    """
    if not sp:
        return []

    query = artist if genre else f"{artist} salsa"
    logger.debug("Spotify search query: '%s'", query)

    try:
        results = sp.search(q=query, type="track", limit=50)
        tracks = results["tracks"]["items"]
    except Exception as e:
        logger.warning("Spotify search error: %s", e)
        return []

    if not tracks:
        return []

    rows: List[Dict] = []
    seen: set = set()
    artist_simp = artist.lower().replace(" ", "")

    for track in tracks:
        track_artists = [a["name"].lower() for a in track.get("artists", [])]
        if not _artist_matches(artist, track_artists):
            continue
        title = track.get("name", "")
        artist_name = track["artists"][0]["name"] if track["artists"] else artist
        k = f"{artist_simp}|{title.lower()}"
        if k in seen:
            continue
        seen.add(k)
        rows.append({
            "artist": artist_name,
            "title": title,
            "query_override": f"{artist_name} {title}",
            "source": "spotify_search",
        })
        if len(rows) >= count:
            break

    logger.info("Spotify encontró %d tracks de '%s'", len(rows), artist)
    return rows


def _artist_matches(search_artist: str, track_artists: List[str]) -> bool:
    s = search_artist.lower().strip()
    for ta in [a.lower() for a in track_artists]:
        if s == ta:
            return True
        if s in ta or ta in s:
            return True
        # normalización sin artículos
        s_norm = _normalize_name(s)
        ta_norm = _normalize_name(ta)
        if len(s_norm) >= 4 and len(ta_norm) >= 4:
            if s_norm in ta_norm or ta_norm in s_norm:
                return True
    return False


def _normalize_name(name: str) -> str:
    articles = {"la", "el", "los", "las", "le", "les", "un", "una", "de", "del", "y", "&"}
    return "".join(w for w in name.split() if w not in articles)


