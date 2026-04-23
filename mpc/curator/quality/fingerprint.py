# mpc/curator/quality/fingerprint.py
# -*- coding: utf-8 -*-
"""Tier 3: fingerprint perceptual con chromaprint + opcional AcoustID match."""

from __future__ import annotations

import shutil

try:
    import acoustid
    _ACOUSTID_AVAILABLE = True
except ImportError:
    _ACOUSTID_AVAILABLE = False


def is_available() -> bool:
    """True si chromaprint (fpcalc) y pyacoustid están instalados."""
    return _ACOUSTID_AVAILABLE and bool(shutil.which("fpcalc"))


def analyze(filepath: str, api_key: str = "") -> dict:
    """Retorna dict con audio_fingerprint y (si api_key) acoustid_mbid."""
    if not is_available():
        return {}
    try:
        duration, fp = acoustid.fingerprint_file(filepath)
    except Exception:
        return {}

    if isinstance(fp, bytes):
        fingerprint_str = fp.decode("ascii", errors="ignore")
    else:
        fingerprint_str = str(fp)

    out = {"audio_fingerprint": fingerprint_str}

    # Opcional: matchear con AcoustID si hay API key
    if api_key:
        try:
            results = list(acoustid.match(api_key, filepath))
            if results:
                score, recording_id, title, artist = results[0]
                if score and score > 0.9 and recording_id:
                    out["acoustid_mbid"] = recording_id
        except Exception:
            pass  # fail silencioso, no bloquear el fingerprint

    return out
