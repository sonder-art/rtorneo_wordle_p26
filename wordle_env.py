"""Wordle environment: game logic for any word length."""

from __future__ import annotations

import random
from collections import Counter
from typing import Iterable


# Feedback encoding:
# 2 = green (correct letter, correct position)
# 1 = yellow (correct letter, wrong position)
# 0 = gray  (letter not present, or already consumed by greens/yellows)


def feedback(secret: str, guess: str) -> tuple[int, ...]:
    """Return feedback tuple for *guess* against *secret* (any word length)."""
    n = len(secret)
    if len(guess) != n:
        raise ValueError(
            f"guess length ({len(guess)}) != secret length ({n})"
        )

    secret = secret.lower()
    guess = guess.lower()

    pat = [0] * n
    remaining = Counter(secret)

    # Pass 1 – greens
    for i, (s, g) in enumerate(zip(secret, guess)):
        if g == s:
            pat[i] = 2
            remaining[g] -= 1

    # Pass 2 – yellows
    for i, (s, g) in enumerate(zip(secret, guess)):
        if pat[i] == 2:
            continue
        if remaining[g] > 0:
            pat[i] = 1
            remaining[g] -= 1

    return tuple(pat)


def filter_candidates(
    candidates: Iterable[str],
    guess: str,
    pattern: tuple[int, ...],
) -> list[str]:
    """Keep only candidates consistent with the observed *pattern*."""
    return [w for w in candidates if feedback(w, guess) == pattern]


class WordleEnv:
    """A single Wordle game.

    Parameters
    ----------
    vocabulary : list[str]
        Valid words (all must have the same length).
    word_length : int
        Expected word length (validated against vocabulary).
    max_guesses : int
        Maximum allowed guesses before the game is lost.
    allow_non_words : bool
        If True, any string of the correct length is accepted as a guess.
    """

    def __init__(
        self,
        vocabulary: list[str],
        word_length: int = 5,
        max_guesses: int = 6,
        allow_non_words: bool = True,
    ) -> None:
        bad = [w for w in vocabulary if len(w) != word_length]
        if bad:
            raise ValueError(
                f"Words with wrong length (expected {word_length}): {bad[:5]}"
            )
        self._vocab = list(vocabulary)
        self._word_length = word_length
        self._max_guesses = max_guesses
        self._allow_non_words = allow_non_words
        self._vocab_set = set(vocabulary)

        # Game state (set by reset)
        self._secret: str | None = None
        self._history: list[tuple[str, tuple[int, ...]]] = []
        self._solved = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, secret: str | None = None) -> None:
        """Start a new game. Random secret if *secret* is None."""
        if secret is not None:
            if secret not in self._vocab_set:
                raise ValueError(f"secret {secret!r} is not in vocabulary")
        self._secret = secret if secret is not None else random.choice(self._vocab)
        self._history = []
        self._solved = False

    def guess(self, word: str) -> tuple[int, ...]:
        """Submit a guess and receive feedback.

        Raises
        ------
        RuntimeError
            If the game is over (solved or out of guesses).
        ValueError
            If *word* has the wrong length or is not in the vocabulary
            (when ``allow_non_words`` is False).
        """
        if self._secret is None:
            raise RuntimeError("Call reset() before guessing")
        if self._solved or len(self._history) >= self._max_guesses:
            raise RuntimeError("Game is already over")
        word = word.lower()
        if len(word) != self._word_length:
            raise ValueError(
                f"Guess length ({len(word)}) != word_length ({self._word_length})"
            )
        if not self._allow_non_words and word not in self._vocab_set:
            raise ValueError(f"{word!r} is not in the vocabulary")

        pat = feedback(self._secret, word)
        self._history.append((word, pat))
        if word == self._secret:
            self._solved = True
        return pat

    def is_solved(self) -> bool:
        return self._solved

    def remaining_guesses(self) -> int:
        return self._max_guesses - len(self._history)

    def game_over(self) -> bool:
        return self._solved or len(self._history) >= self._max_guesses

    @property
    def history(self) -> list[tuple[str, tuple[int, ...]]]:
        return list(self._history)

    @property
    def secret(self) -> str:
        """Reveal the secret word (only after game over)."""
        if self._secret is None:
            raise RuntimeError("No game in progress")
        if not self.game_over():
            raise RuntimeError("Game is still in progress")
        return self._secret

    @property
    def word_length(self) -> int:
        return self._word_length

    @property
    def max_guesses(self) -> int:
        return self._max_guesses
