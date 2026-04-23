# mpc/curator/quality/score.py
# -*- coding: utf-8 -*-
"""Score compuesto 0-100 basado en métricas de los 3 tiers disponibles."""


def compute(metrics: dict) -> int:
    """Calcula score 0-100. Funciona con tiers parciales (NULL se ignora)."""
    score = 50  # baseline

    # ── Tier 1 ────────────────────────────────────────────────────────────
    br = metrics.get("bitrate_kbps") or 0
    if br >= 320:
        score += 15
    elif br >= 256:
        score += 10
    elif br >= 192:
        score += 5
    elif 0 < br < 128:
        score -= 10

    sr = metrics.get("sample_rate") or 0
    if sr >= 44100:
        score += 5

    ch = metrics.get("channels") or 0
    if ch >= 2:
        score += 5

    # ── Tier 2 ────────────────────────────────────────────────────────────
    lufs = metrics.get("lufs_integrated")
    if lufs is not None:
        if -16 <= lufs <= -10:
            score += 15  # rango típico saludable
        elif lufs < -20 or lufs > -6:
            score -= 10  # extremos

    peak = metrics.get("true_peak_db")
    if peak is not None and peak > 0:
        score -= 15  # clipping penalty fuerte

    return max(0, min(100, score))
