# mpc/download/steps/base.py
# -*- coding: utf-8 -*-
"""
Interfaz base para todos los pasos del DownloadEngine.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseStep(ABC):
    """
    Cada step recibe un contexto mutable (dict) y lo enriquece.

    El contexto viaja por todos los pasos secuencialmente:
      ctx["request"]       → DownloadRequest original
      ctx["video_id"]      → str (seteado por SearchStep)
      ctx["candidates"]    → List[Dict] (candidatos crudos de YouTube)
      ctx["best_meta"]     → Dict (metadata del candidato elegido)
      ctx["genre_slug"]    → str (seteado por ClassifierStep)
      ctx["confidence"]    → float
      ctx["rationale"]     → str
      ctx["filepath"]      → str (seteado por DownloaderStep)
      ctx["quota"]         → Dict {units: int, calls: dict}
      ctx["skip"]          → True si un step previo indica saltar descarga
      ctx["skip_reason"]   → str
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def run(self, ctx: Dict[str, Any]) -> None:
        """Modifica ctx in-place. Puede setear ctx['skip']=True para cortocircuitar."""
        ...
