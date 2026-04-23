# mpc/curator/quality/ffprobe.py
# -*- coding: utf-8 -*-
"""Tier 1: análisis técnico vía ffprobe (ya incluido con ffmpeg)."""

from __future__ import annotations

import json
import shutil
import subprocess


def is_available() -> bool:
    return bool(shutil.which("ffprobe"))


def analyze(filepath: str) -> dict:
    """Extrae info técnica. Retorna dict con bitrate_kbps, sample_rate,
    codec, channels, duration_sec. Vacío si falla."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return {}
        data = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return {}

    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        return {}
    s = streams[0]
    fmt = data.get("format", {})

    # Bitrate: prefiere stream, fallback a format
    bitrate_raw = s.get("bit_rate") or fmt.get("bit_rate") or "0"
    try:
        bitrate_kbps = int(bitrate_raw) // 1000
    except (ValueError, TypeError):
        bitrate_kbps = 0

    try:
        sample_rate = int(s.get("sample_rate") or 0)
    except (ValueError, TypeError):
        sample_rate = 0

    try:
        channels = int(s.get("channels") or 0)
    except (ValueError, TypeError):
        channels = 0

    try:
        duration = float(fmt.get("duration") or s.get("duration") or 0)
    except (ValueError, TypeError):
        duration = 0.0

    out = {
        "bitrate_kbps": bitrate_kbps,
        "sample_rate": sample_rate,
        "codec": s.get("codec_name", ""),
        "channels": channels,
        "duration_sec": round(duration, 2),
    }
    return out
