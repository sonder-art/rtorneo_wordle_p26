"""Entropy strategy: maximise expected information gain per guess."""

from __future__ import annotations

import math
import random
from collections import defaultdict

from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates

# Performance caps to stay within 5 s/game on 20k-word vocabularies
_MAX_GUESS_POOL = 200      # max guesses to evaluate
_MAX_EVAL_CANDIDATES = 500  # max candidates to compute feedback against


class EntropyStrategy(Strategy):
    """Select the guess that maximises Shannon entropy of the feedback partition.

    For each candidate guess *g*, the remaining candidates are partitioned by
    the feedback pattern they would produce.  The guess with the highest
    entropy H = -sum(p_i * log2(p_i)) is chosen because it maximises expected
    information gain.

    Performance budget (5 s/game with 20k-word vocabularies):
      - |candidates| <= 2: return immediately.
      - Guess pool capped at 200 words.
      - Candidate evaluation set capped at 500 words.
      - After first guess, candidates typically drop to <500 (exact).
    """

    @property
    def name(self) -> str:
        return "Entropy"

    def begin_game(self, config: GameConfig) -> None:
        self._vocab = list(config.vocabulary)
        self._config = config
        self._rng = random.Random(42)

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        # Filter candidates consistent with all feedback so far
        candidates = self._vocab
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)

        if not candidates:
            return self._vocab[0]
        if len(candidates) <= 2:
            return candidates[0]

        candidate_set = set(candidates)

        # Build guess pool (capped for performance)
        if len(candidates) <= _MAX_GUESS_POOL:
            guess_pool = candidates
        else:
            guess_pool = self._rng.sample(candidates, _MAX_GUESS_POOL)

        # Subsample candidates for entropy evaluation if too many
        if len(candidates) <= _MAX_EVAL_CANDIDATES:
            eval_candidates = candidates
        else:
            eval_candidates = self._rng.sample(candidates, _MAX_EVAL_CANDIDATES)

        best_guess = candidates[0]
        best_entropy = -1.0
        n = len(eval_candidates)

        for g in guess_pool:
            # Partition eval_candidates by feedback pattern
            partition: dict[int, int] = defaultdict(int)
            for c in eval_candidates:
                pat = feedback(c, g)
                key = _encode_pattern(pat)
                partition[key] += 1

            # Compute entropy
            ent = 0.0
            for count in partition.values():
                p = count / n
                ent -= p * math.log2(p)

            # Prefer candidates over non-candidates on ties
            is_candidate = g in candidate_set
            if ent > best_entropy or (
                ent == best_entropy and is_candidate and best_guess not in candidate_set
            ):
                best_entropy = ent
                best_guess = g

        return best_guess


def _encode_pattern(pat: tuple[int, ...]) -> int:
    """Encode a feedback tuple as a single integer for fast hashing."""
    val = 0
    for i, c in enumerate(pat):
        val += c * (3 ** i)
    return val
