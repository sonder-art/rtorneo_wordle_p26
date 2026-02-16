"""Random strategy: pick uniformly at random from remaining candidates."""

from __future__ import annotations

import random

from strategy import Strategy, GameConfig
from wordle_env import filter_candidates


class RandomStrategy(Strategy):
    """Guess a random word from the set of remaining candidates."""

    @property
    def name(self) -> str:
        return "Random"

    def begin_game(self, config: GameConfig) -> None:
        self._candidates = list(config.vocabulary)

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        # Re-filter from scratch (simple & correct)
        candidates = self._candidates
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)
        if not candidates:
            # Fallback: shouldn't happen with a valid vocabulary
            return self._candidates[0]
        return random.choice(candidates)
