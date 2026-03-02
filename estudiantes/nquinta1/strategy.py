"""Strategy template — copy this directory to estudiantes/<your_team>/

Rename the class and the ``name`` property, then implement your logic
in the ``guess`` method.
"""

from __future__ import annotations

from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates


import math
from collections import Counter, defaultdict


class MiEstrategia_nquinta1(Strategy):

    @property
    def name(self) -> str:
        return "MiEstrategia_nquinta1"

    def begin_game(self, config: GameConfig) -> None:
        self._config = config
        self._vocab = list(config.vocabulary)
        self._L = config.word_length

        if config.mode == "frequency":
            self._p = dict(config.probabilities)
        else:
            self._p = {w: 1.0 for w in self._vocab}

        self._fb_cache = {}

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:

        candidates = self._vocab
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)

        if not history:
            return self._best_cover_word(candidates)

        if len(candidates) <= 5:
            return max(candidates, key=lambda w: self._p.get(w, 1.0))

        best_word = None
        best_entropy = -1

        for guess_word in candidates[:200]:
            entropy = self._expected_entropy(guess_word, candidates)
            if entropy > best_entropy:
                best_entropy = entropy
                best_word = guess_word

        return best_word if best_word else candidates[0]

    def _feedback(self, guess, secret):
        key = (guess, secret)
        if key not in self._fb_cache:
            self._fb_cache[key] = feedback(guess, secret)
        return self._fb_cache[key]

    def _expected_entropy(self, guess, candidates):
        counts = defaultdict(float)
        total = 0

        for secret in candidates:
            weight = self._p.get(secret, 1.0)
            pat = self._feedback(guess, secret)
            counts[pat] += weight
            total += weight

        entropy = 0
        for w in counts.values():
            p = w / total
            if p > 0:
                entropy -= p * math.log2(p)

        return entropy

    def _best_cover_word(self, words):
        letter_counts = Counter()
        for w in words:
            letter_counts.update(set(w))

        def score(w):
            return sum(letter_counts[c] for c in set(w))

        return max(words, key=score)