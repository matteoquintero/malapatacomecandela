# mpc/curator/status.py
# -*- coding: utf-8 -*-
"""Enum de estados que puede tener un track según curator."""


class CuratorStatus:
    """Valores posibles de la columna curator_status (enfocado en AUDIO)."""

    OK = "ok"
    NEEDS_THUMBNAIL = "needs_thumbnail"
    NEEDS_TAGS = "needs_tags"
    NEEDS_METADATA = "needs_metadata"
    NEEDS_RENAME = "needs_rename"
    NEEDS_MOVE = "needs_move"
    DUPLICATE = "duplicate"
    ORPHAN = "orphan"
    MISSING = "missing"

    ALL = (
        OK, NEEDS_THUMBNAIL, NEEDS_TAGS, NEEDS_METADATA, NEEDS_RENAME,
        NEEDS_MOVE, DUPLICATE, ORPHAN, MISSING,
    )

    PRIORITY = (
        MISSING, ORPHAN, DUPLICATE, NEEDS_MOVE, NEEDS_RENAME,
        NEEDS_METADATA, NEEDS_THUMBNAIL, NEEDS_TAGS, OK,
    )


class VideoStatus:
    """Valores posibles de la columna video_status (independiente del audio)."""

    NOT_READY         = "not_ready"         # audio no está ok → no evaluar video
    NEEDS_VIDEO       = "needs_video"       # audio ok, sin video → candidato
    VIDEO_OK          = "video_ok"          # video_filepath válido en disco
    VIDEO_UNAVAILABLE = "video_unavailable" # intentado, sin match en YouTube
    VIDEO_REJECTED    = "video_rejected"    # usuario rechazó explícitamente

    ALL = (NOT_READY, NEEDS_VIDEO, VIDEO_OK, VIDEO_UNAVAILABLE, VIDEO_REJECTED)

    # Estados terminales: los preservamos entre re-audits (no los sobreescribe
    # el auditor automáticamente).
    TERMINAL = (VIDEO_UNAVAILABLE, VIDEO_REJECTED)
