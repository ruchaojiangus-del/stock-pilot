"""A-share strong-wave selector skill runtime."""

from .scoring import ScoreConfig, ScoreResult, score_candidate
from .selector import SelectionConfig, run_selection

__all__ = [
    "ScoreConfig",
    "ScoreResult",
    "SelectionConfig",
    "score_candidate",
    "run_selection",
]
