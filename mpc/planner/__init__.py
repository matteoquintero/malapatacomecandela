# mpc/planner/__init__.py — compat shim → mpc.discovery
from mpc.discovery.planner import (
    classify_request, is_complex_request, is_blocked, blocked_message, detect_direct_genre
)
from mpc.discovery.llm_planner import llm_plan

__all__ = [
    "classify_request", "is_complex_request", "is_blocked",
    "blocked_message", "detect_direct_genre", "llm_plan",
]
