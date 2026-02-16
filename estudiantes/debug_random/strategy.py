"""Debug student strategy — Random (verifies student auto-discovery works)."""

from __future__ import annotations

import random

from strategy import Strategy, GameConfig
from wordle_env import filter_candidates


class RandomStudentStrategy(Strategy):
    """Random strategy submitted as a student for debugging auto-discovery."""

    @property
    def name(self) -> str:
        return "Random_debug"

    def begin_game(self, config: GameConfig) -> None:
        self._candidates = list(config.vocabulary)

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        candidates = self._candidates
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)
        if not candidates:
            return self._candidates[0]
        return random.choice(candidates)
