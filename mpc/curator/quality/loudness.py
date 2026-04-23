# mpc/curator/quality/loudness.py
# -*- coding: utf-8 -*-
"""Tier 2: loudness EBU R128 vía pyloudnorm. Graceful fallback si no instalado."""

from __future__ import annotations

try:
    import pyloudnorm as pyln
    import soundfile as sf
    import numpy as np
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def is_available() -> bool:
    return _AVAILABLE


def analyze(filepath: str) -> dict:
    """Retorna dict con lufs_integrated, true_peak_db, dynamic_range."""
    if not _AVAILABLE:
        return {}
    try:
        data, rate = sf.read(filepath)
        if data.size == 0:
            return {}
        meter = pyln.Meter(rate)
        lufs = meter.integrated_loudness(data)
        # True peak aproximado (sin oversampling)
        peak_linear = float(np.abs(data).max())
        peak_db = 20 * np.log10(max(peak_linear, 1e-10))
        # Dynamic range: LRA (loudness range)
        try:
            dr = meter.loudness_range(data)
        except Exception:
            dr = None
        return {
            "lufs_integrated": round(float(lufs), 2),
            "true_peak_db": round(float(peak_db), 2),
            "dynamic_range": round(float(dr), 2) if dr is not None else None,
        }
    except Exception:
        return {}
