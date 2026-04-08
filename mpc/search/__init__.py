# mpc/search/__init__.py — compat shim → mpc.discovery
# Este módulo se mantiene solo para compatibilidad con imports antiguos.
# El código nuevo debe importar desde mpc.discovery.*
from mpc.discovery.engine import SearchEngine, SearchPlan
from mpc.discovery.intent import QueryIntent, SearchRequest
from mpc.discovery.candidate import Candidate, CandidateSet

__all__ = ["SearchEngine", "SearchPlan", "QueryIntent", "SearchRequest", "Candidate", "CandidateSet"]
