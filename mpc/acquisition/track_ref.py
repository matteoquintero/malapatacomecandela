# mpc/download/track_ref.py
# -*- coding: utf-8 -*-
"""
TrackRef: referencia a un track descargable, independiente de plataforma.

Reemplaza el concepto de "video_id" (YouTube-específico) con un objeto
genérico que soporta cualquier fuente que yt-dlp o spotdl pueda manejar.
"""

from dataclasses import dataclass, field

# Constantes de plataforma
YOUTUBE     = "youtube"
SOUNDCLOUD  = "soundcloud"
SPOTIFY     = "spotify"    # spotdl
DIRECT      = "direct"     # URL directa


@dataclass
class TrackRef:
    url: str          # URL completa descargable (yt-dlp / spotdl)
    platform: str     # YOUTUBE | SOUNDCLOUD | SPOTIFY | DIRECT
    display_id: str   # ID corto para logs y manifest (video_id, slug, etc.)
    thumbnail_url: str = ""  # URL del artwork; vacío si la plataforma no lo provee


def infer_platform(url: str) -> str:
    """Infiere la plataforma desde la URL."""
    if "youtube.com" in url or "youtu.be" in url:
        return YOUTUBE
    if "soundcloud.com" in url:
        return SOUNDCLOUD
    if "spotify.com" in url or url.startswith("spotify:"):
        return SPOTIFY
    return DIRECT


def youtube_ref(video_id: str, image_type: str = "hq") -> TrackRef:
    """Construye un TrackRef para un video de YouTube."""
    thumb = (
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        if image_type == "max"
        else f"https://i3.ytimg.com/vi/{video_id}/hqdefault.jpg"
    )
    return TrackRef(
        url=f"https://www.youtube.com/watch?v={video_id}",
        platform=YOUTUBE,
        display_id=video_id,
        thumbnail_url=thumb,
    )


def ref_from_candidate(candidate: dict, image_type: str = "hq") -> TrackRef:
    """
    Construye un TrackRef desde el dict de un candidato de búsqueda.
    Si el candidato ya tiene 'url', lo usa directo.
    Si solo tiene 'video_id', asume YouTube.
    """
    url = candidate.get("url") or ""
    platform = candidate.get("platform") or ""
    display_id = candidate.get("display_id") or candidate.get("video_id") or ""
    thumbnail_url = candidate.get("thumbnail_url") or ""

    if url and platform:
        return TrackRef(url=url, platform=platform,
                        display_id=display_id or url, thumbnail_url=thumbnail_url)

    # Compat: candidato antiguo con solo video_id (YouTube asumido)
    vid = candidate.get("video_id") or ""
    if vid:
        return youtube_ref(vid, image_type)

    # Último recurso: URL directa
    return TrackRef(url=url or display_id, platform=DIRECT,
                    display_id=display_id or url, thumbnail_url="")
