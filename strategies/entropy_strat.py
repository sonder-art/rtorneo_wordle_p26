"""Entropy strategy: maximise expected information gain per guess.

If precomputed decision trees exist (from precompute_trees.py), uses
instant tree lookups for the first few guesses. Falls back to live
entropy computation when the tree doesn't cover a position (typically
when candidates are small enough for it to be instant).
"""

from __future__ import annotations

import math
import pickle
import random
from collections import defaultdict
from pathlib import Path

from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates

# Performance caps for live fallback computation
_MAX_GUESS_POOL = 200      # max guesses to evaluate
_MAX_EVAL_CANDIDATES = 500  # max candidates to compute feedback against

_TREE_DIR = Path(__file__).resolve().parent.parent / "data" / "trees"


class EntropyStrategy(Strategy):
    """Select the guess that maximises Shannon entropy of the feedback partition.

    Uses precomputed decision trees (if available) for instant lookups
    on the first few guesses, then falls back to live entropy computation
    once candidates are small enough.
    """

    def __init__(self):
        self._trees: dict[tuple[int, str], dict] = {}
        if _TREE_DIR.is_dir():
            for wl in [4, 5, 6]:
                for mode in ["uniform", "frequency"]:
                    tree_path = _TREE_DIR / f"tree_{wl}_{mode}.pkl"
                    if tree_path.exists():
                        try:
                            with open(tree_path, "rb") as f:
                                self._trees[(wl, mode)] = pickle.load(f)
                        except Exception:
                            pass

    @property
    def name(self) -> str:
        return "Entropy"

    def begin_game(self, config: GameConfig) -> None:
        self._vocab = list(config.vocabulary)
        self._config = config
        self._rng = random.Random(42)
        self._tree = self._trees.get(
            (config.word_length, config.mode), {})

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        # Try precomputed tree first (instant lookup)
        path = tuple(pat for _, pat in history)
        if path in self._tree:
            return self._tree[path]

        # Fallback: live entropy computation
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
            partition: dict[int, int] = defaultdict(int)
            for c in eval_candidates:
                pat = feedback(c, g)
                key = _encode_pattern(pat)
                partition[key] += 1

            ent = 0.0
            for count in partition.values():
                p = count / n
                ent -= p * math.log2(p)

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
