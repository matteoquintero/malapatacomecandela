# mpc/download/request.py
# -*- coding: utf-8 -*-
"""
DownloadRequest: contrato de entrada para el DownloadEngine.
Un request por canción; el engine decide las estrategias.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DownloadRequest:
    artist: str
    title: str

    # Si viene del CSV con query_override (video ID, URL, o query custom)
    query_override: Optional[str] = None

    # Género ya conocido (desde CSV o planner); si está presente se omite el clasificador
    genre: Optional[str] = None

    # Tipo de thumbnail para el artwork ("hq" o "max")
    image_type: str = "hq"

    # Si es True: busca y clasifica, pero no descarga ni escribe al manifest
    dry_run: bool = False
