# mpc/discovery/ — BC1: Descubrimiento
# Responsabilidad: descubrir candidatos musicales dado un intent.
from mpc.discovery.intent import QueryIntent, SearchRequest
from mpc.discovery.candidate import Candidate, CandidateSet
from mpc.discovery.engine import SearchEngine, SearchPlan
from mpc.discovery.events import CandidatesDiscovered
from mpc.discovery.use_cases import DiscoverTracksUseCase

__all__ = [
    "QueryIntent", "SearchRequest",
    "Candidate", "CandidateSet",
    "SearchEngine", "SearchPlan",
    "CandidatesDiscovered",
    "DiscoverTracksUseCase",
]
