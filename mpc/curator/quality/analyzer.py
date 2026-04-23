# mpc/curator/quality/analyzer.py
# -*- coding: utf-8 -*-
"""Orquestador de análisis de calidad (tiers 1+2+3)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from mpc.curator.quality import ffprobe, loudness, fingerprint, score
from mpc.library.repository import TrackRepository


class QualityAnalyzer:
    def __init__(self, repo: TrackRepository, acoustid_key: str = ""):
        self.repo = repo
        self.acoustid_key = acoustid_key

    def resolve_tier(self, requested: Optional[int]) -> int:
        """Calcula el tier máximo disponible según deps instaladas."""
        max_tier = 0
        if ffprobe.is_available():
            max_tier = 1
        if loudness.is_available():
            max_tier = 2
        if fingerprint.is_available():
            max_tier = 3
        if requested is None:
            return max_tier
        return min(requested, max_tier)

    def run(
        self,
        tier: Optional[int] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict:
        effective_tier = self.resolve_tier(tier)
        if effective_tier == 0:
            print("❌ Ni ffprobe está disponible — no se puede analizar nada.")
            return {"tier": 0, "total": 0, "ok": 0, "failed": 0}

        tracks = self.repo.without_quality_analyzed(force=force)
        if limit:
            tracks = tracks[:limit]

        print(f"📊 Analizando {len(tracks)} tracks (tier {effective_tier})...")
        if effective_tier >= 2 and not loudness.is_available():
            print("   ⚠️  tier 2 solicitado pero pyloudnorm no instalado")
        if effective_tier >= 3 and not fingerprint.is_available():
            print("   ⚠️  tier 3 solicitado pero chromaprint/pyacoustid no instalados")

        stats = {
            "tier": effective_tier,
            "total": len(tracks),
            "ok": 0,
            "failed": 0,
            "skipped": 0,
            "by_score": {"90+": 0, "70-89": 0, "50-69": 0, "<50": 0},
        }

        for i, t in enumerate(tracks, 1):
            fp = t.get("filepath") or ""
            label = f"[{i}/{len(tracks)}] {t['artist']} - {t['title']}"

            if not fp or not Path(fp).is_file():
                print(f"{label}  ⚠️  archivo inexistente")
                stats["skipped"] += 1
                continue

            metrics = {}
            if effective_tier >= 1:
                metrics.update(ffprobe.analyze(fp))
            if effective_tier >= 2:
                metrics.update(loudness.analyze(fp))
            if effective_tier >= 3:
                metrics.update(fingerprint.analyze(fp, self.acoustid_key))

            if not metrics:
                print(f"{label}  ❌ no se pudo analizar")
                stats["failed"] += 1
                continue

            metrics["audio_quality_score"] = score.compute(metrics)

            # Resumen compacto
            summary_parts = []
            if metrics.get("bitrate_kbps"):
                summary_parts.append(f"br={metrics['bitrate_kbps']}k")
            if metrics.get("lufs_integrated") is not None:
                summary_parts.append(f"lufs={metrics['lufs_integrated']}")
            if metrics.get("true_peak_db") is not None:
                summary_parts.append(f"peak={metrics['true_peak_db']}dB")
            if metrics.get("audio_fingerprint"):
                summary_parts.append("fp=✓")
            summary_parts.append(f"score={metrics['audio_quality_score']}")
            print(f"{label}  {' '.join(summary_parts)}")

            # Distribución de scores
            sc = metrics["audio_quality_score"]
            if sc >= 90:
                stats["by_score"]["90+"] += 1
            elif sc >= 70:
                stats["by_score"]["70-89"] += 1
            elif sc >= 50:
                stats["by_score"]["50-69"] += 1
            else:
                stats["by_score"]["<50"] += 1

            if not dry_run:
                self.repo.update_quality(t["track_id"], metrics)

            stats["ok"] += 1

        return stats
