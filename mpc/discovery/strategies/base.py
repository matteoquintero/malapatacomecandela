# mpc/discovery/strategies/base.py
# -*- coding: utf-8 -*-
"""
BaseStrategy: contrato que deben cumplir todas las estrategias.
Cada estrategia encapsula UNA fuente de datos y devuelve Candidates con
confidence y evidence propios. No decide cuántos resultados usar; eso
es responsabilidad del Engine y el Ranker.
"""

from abc import ABC, abstractmethod
from typing import List
from mpc.discovery.candidate import Candidate
from mpc.discovery.intent import SearchRequest


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def execute(self, request: SearchRequest) -> List[Candidate]:
        """Ejecuta la estrategia y devuelve candidatos sin deduplicar."""
        ...

    def __repr__(self) -> str:
        return f"<Strategy:{self.name}>"
