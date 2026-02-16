"""Max-probability strategy: always guess the most probable remaining candidate."""

from __future__ import annotations

from strategy import Strategy, GameConfig
from wordle_env import filter_candidates


class MaxProbStrategy(Strategy):
    """Always guess the most probable remaining candidate.

    Under ``uniform`` mode this picks alphabetically first (all equal).
    Under ``frequency`` mode it picks the word with highest probability.
    """

    @property
    def name(self) -> str:
        return "MaxProb"

    def begin_game(self, config: GameConfig) -> None:
        self._probs = config.probabilities
        # Pre-sort by descending probability, then alphabetically for ties
        self._candidates = sorted(
            config.vocabulary, key=lambda w: (-self._probs.get(w, 0), w)
        )

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        candidates = self._candidates
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)
        if not candidates:
            return self._candidates[0]
        # Already sorted by probability — return best
        return candidates[0]
