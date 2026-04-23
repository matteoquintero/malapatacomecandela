# mpc/curator/quality/__init__.py
# -*- coding: utf-8 -*-
"""
Análisis de calidad de audio en 3 tiers incrementales:
  Tier 1: ffprobe (bitrate, sample_rate, codec, channels, duration)
  Tier 2: pyloudnorm (LUFS, true peak, dynamic range)
  Tier 3: chromaprint + pyacoustid (fingerprint + opcional AcoustID match)
"""

from mpc.curator.quality.analyzer import QualityAnalyzer

__all__ = ["QualityAnalyzer"]
