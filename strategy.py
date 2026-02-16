"""Abstract base class for Wordle strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GameConfig:
    """All information a strategy receives at the start of each game.

    Attributes
    ----------
    word_length : int
        Number of letters in each word (4, 5, or 6).
    vocabulary : tuple[str, ...]
        All valid words for this game variant (immutable).  The secret
        word is always drawn from this set.
    mode : str
        Probability mode: ``"uniform"`` or ``"frequency"``.
    probabilities : dict[str, float]
        Mapping of word -> probability (sums to 1).  Under ``"uniform"``
        every word has equal probability; under ``"frequency"`` the
        probabilities are sigmoid-weighted by corpus frequency.
    max_guesses : int
        Maximum number of guesses allowed per game (typically 6).
    allow_non_words : bool
        If True, guesses are **not** restricted to the vocabulary.
        Any lowercase string of the correct length is accepted.
        This lets strategies guess arbitrary letter combinations for
        better information discovery.
    """

    word_length: int
    vocabulary: tuple[str, ...]
    mode: str
    probabilities: dict[str, float]
    max_guesses: int
    allow_non_words: bool = True


class Strategy(ABC):
    """Interface that every Wordle strategy must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name (used in reports)."""
        ...

    def begin_game(self, config: GameConfig) -> None:
        """Called at the start of each game.

        Use this for precomputation (e.g. building pattern tables).
        The *config* object provides full game information: vocabulary,
        probabilities, mode, word length, and max guesses.

        The default implementation does nothing.
        """

    @abstractmethod
    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        """Return the next guess given the history of (guess, feedback) pairs."""
        ...

    def end_game(self, secret: str, solved: bool, num_guesses: int) -> None:
        """Called at the end of each game.

        Use this for learning, logging, or statistics.
        The default implementation does nothing.
        """
