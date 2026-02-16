"""Word-list loading utilities (self-contained).

Supports two formats:
  - Plain text: one word per line (uniform weights)
  - CSV with header ``word,count``: word frequencies from OpenSLR

And two probability modes:
  - ``uniform``:  every word has equal probability  p = 1/N
  - ``frequency``: probability proportional to a sigmoid of log-frequency
"""

from __future__ import annotations

import csv
import math
import random
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


_DIR = Path(__file__).resolve().parent


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


# ------------------------------------------------------------------
# Lexicon dataclass
# ------------------------------------------------------------------

@dataclass
class Lexicon:
    """A word list with associated probabilities."""
    words: list[str]
    probs: dict[str, float]   # word -> probability (sums to 1)
    mode: str                 # "uniform" or "frequency"


# ------------------------------------------------------------------
# Sigmoid weighting (for frequency mode)
# ------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _sigmoid_weights(
    raw_counts: dict[str, int],
    steepness: float = 1.5,
) -> dict[str, float]:
    """Map raw counts to [0,1] via sigmoid on log-count, then normalize."""
    if not raw_counts:
        return {}
    log_counts = {w: math.log(c + 1) for w, c in raw_counts.items()}
    mu = sum(log_counts.values()) / len(log_counts)
    weights = {w: _sigmoid(steepness * (lc - mu)) for w, lc in log_counts.items()}
    total = sum(weights.values())
    return {w: v / total for w, v in weights.items()}


# ------------------------------------------------------------------
# Distribution perturbation (shock)
# ------------------------------------------------------------------

def perturb_probabilities(
    probs: dict[str, float],
    noise_scale: float = 0.05,
    seed: int | None = None,
) -> dict[str, float]:
    """Apply white-noise perturbation to a probability distribution.

    Each probability p_i is multiplied by (1 + epsilon_i) where
    epsilon_i ~ Uniform(-noise_scale, +noise_scale), then renormalized.

    This preserves the overall shape of the distribution while making
    exact probability values slightly unpredictable.

    Parameters
    ----------
    probs : dict[str, float]
        Original word -> probability mapping.
    noise_scale : float
        Perturbation magnitude (e.g. 0.05 for 5% noise).
    seed : int or None
        Random seed for reproducibility.

    Returns
    -------
    dict[str, float]
        Perturbed probability distribution (sums to 1).
    """
    rng = random.Random(seed)
    perturbed = {}
    for w, p in probs.items():
        factor = 1.0 + rng.uniform(-noise_scale, noise_scale)
        perturbed[w] = max(p * factor, 1e-12)
    total = sum(perturbed.values())
    return {w: v / total for w, v in perturbed.items()}


# ------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------

def _load_txt(path: Path, word_length: int) -> tuple[list[str], dict[str, int]]:
    """Load plain-text word list (one word per line). Counts are all 1."""
    pattern = re.compile(rf"^[a-z]{{{word_length}}}$")
    seen: set[str] = set()
    words: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        w = _strip_accents(raw.strip().lower())
        if not w or w in seen:
            continue
        if pattern.match(w):
            seen.add(w)
            words.append(w)
    words.sort()
    counts = {w: 1 for w in words}
    return words, counts


def _load_csv(path: Path, word_length: int) -> tuple[list[str], dict[str, int]]:
    """Load CSV with ``word,count`` header."""
    pattern = re.compile(rf"^[a-z]{{{word_length}}}$")
    seen: set[str] = set()
    words: list[str] = []
    counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            w = _strip_accents(row["word"].strip().lower())
            if not w or w in seen:
                continue
            if not pattern.match(w):
                continue
            c = int(row["count"])
            if c <= 0:
                continue
            seen.add(w)
            words.append(w)
            counts[w] = c
    words.sort()
    return words, counts


def load_lexicon(
    path: str | None = None,
    word_length: int = 5,
    mode: str = "uniform",
) -> Lexicon:
    """Load words and build a probability distribution.

    Parameters
    ----------
    path : str or None
        Path to a ``.txt`` (one word/line) or ``.csv`` (word,count).
        None falls back to ``data/spanish_{word_length}letter.csv`` if it
        exists, else ``data/mini_spanish_{word_length}.txt``.
    word_length : int
        Only keep words of this exact length.
    mode : ``"uniform"`` or ``"frequency"``
        ``uniform`` — equal probability for every word.
        ``frequency`` — sigmoid-smoothed frequency weighting.

    Returns
    -------
    Lexicon
    """
    if mode not in ("uniform", "frequency"):
        raise ValueError(f"mode must be 'uniform' or 'frequency', got {mode!r}")

    # Resolve path
    if path is not None:
        src = Path(path)
    else:
        # Prefer the downloaded CSV, fall back to mini txt
        csv_path = _DIR / "data" / f"spanish_{word_length}letter.csv"
        mini_path = _DIR / "data" / f"mini_spanish_{word_length}.txt"
        if csv_path.exists():
            src = csv_path
        elif mini_path.exists():
            src = mini_path
        else:
            raise FileNotFoundError(
                f"No word list found for {word_length}-letter words. "
                f"Looked for:\n  {csv_path}\n  {mini_path}\n"
                f"Run: python download_words.py --length {word_length}"
            )

    if not src.exists():
        raise FileNotFoundError(f"Word list not found: {src}")

    # Load
    if src.suffix == ".csv":
        words, counts = _load_csv(src, word_length)
    else:
        words, counts = _load_txt(src, word_length)

    if not words:
        raise ValueError(f"No {word_length}-letter words found in {src}")

    # Build probabilities
    if mode == "uniform":
        p = 1.0 / len(words)
        probs = {w: p for w in words}
    else:
        probs = _sigmoid_weights(counts)

    return Lexicon(words=words, probs=probs, mode=mode)
