#!/usr/bin/env python3
"""
Download and prepare a clean Spanish word list for the Wordle tournament.

Pipeline:
  1. Download OpenSLR SLR21 word frequencies (CC BY-SA 3.0)
  2. Download Hunspell-validated Spanish dictionary (xavier-hernandez/spanish-wordlist)
  3. Cross-reference: keep only words present in BOTH sources
  4. Output CSV with word,count (sorted by frequency descending)

This produces a clean corpus of real Spanish words (~1.7k-3.7k per length)
instead of the raw ~20k OpenSLR dump which contains foreign names and garbage.

Usage:
    python download_words.py                 # default: 5-letter words
    python download_words.py --length 6      # 6-letter words
    python download_words.py --all-lengths   # lengths 4, 5, and 6
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import tarfile
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path


_DIR = Path(__file__).resolve().parent
_CACHE = _DIR / "data" / ".cache"

OPENSLR_URL = "https://www.openslr.org/resources/21/es_wordlist.json.tgz"
HUNSPELL_URL = (
    "https://raw.githubusercontent.com/xavier-hernandez/"
    "spanish-wordlist/master/text/spanish_words.txt"
)


# ------------------------------------------------------------------
# Download helpers
# ------------------------------------------------------------------

def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  (cached) {dest.name}")
        return
    print(f"  Downloading {url} ...")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved {dest.name}")


def _extract_json(tgz: Path) -> Path:
    out = _CACHE / "es_wordlist.json"
    if out.exists():
        return out
    print("  Extracting JSON from tarball ...")
    with tarfile.open(tgz, "r:gz") as tf:
        for m in tf.getmembers():
            if m.name.endswith(".json"):
                data = tf.extractfile(m)
                if data is None:
                    continue
                out.write_bytes(data.read())
                return out
    raise RuntimeError("No JSON found in tarball")


# ------------------------------------------------------------------
# Normalization (matches lexicon.py: strip accents, preserve ñ)
# ------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Strip accent marks but preserve ñ."""
    result = []
    for ch in text:
        if ch == "ñ":
            result.append("ñ")
        else:
            decomposed = unicodedata.normalize("NFD", ch)
            result.append(
                "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
            )
    return "".join(result)


def _normalize(token: str) -> str:
    return _strip_accents(token.strip().lower())


# ------------------------------------------------------------------
# Hunspell dictionary loading
# ------------------------------------------------------------------

def _load_hunspell(path: Path) -> set[str]:
    """Load Hunspell word list and normalize to our format."""
    raw = path.read_bytes()
    # Try UTF-8 first, fall back to ISO-8859-1 (latin1)
    for enc in ("utf-8", "iso-8859-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Cannot decode {path}")

    words: set[str] = set()
    for line in text.splitlines():
        w = _normalize(line)
        if w:
            words.add(w)
    print(f"  Hunspell dictionary: {len(words)} words loaded")
    return words


# ------------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------------

def build_wordlist(
    word_length: int = 5,
    hunspell_words: set[str] | None = None,
    min_count: int = 2,
) -> Path:
    """Download OpenSLR data, filter against Hunspell, produce CSV."""
    tgz_path = _CACHE / "es_wordlist.json.tgz"
    json_path = _CACHE / "es_wordlist.json"

    if not json_path.exists():
        _download(OPENSLR_URL, tgz_path)
        json_path = _extract_json(tgz_path)
    else:
        print(f"  (cached) {json_path.name}")

    print(f"  Parsing {json_path.name} ...")
    data: dict = json.loads(json_path.read_text(encoding="utf-8"))

    pattern = re.compile(rf"^[a-zñ]{{{word_length}}}$")
    counts: Counter[str] = Counter()
    for raw_word, raw_count in data.items():
        w = _normalize(str(raw_word))
        if not pattern.match(w):
            continue
        try:
            c = int(raw_count)
        except (ValueError, TypeError):
            continue
        if c > 0:
            counts[w] += c

    openslr_total = len(counts)

    # Filter against Hunspell dictionary
    if hunspell_words is not None:
        counts = Counter({w: c for w, c in counts.items() if w in hunspell_words})

    # Filter by minimum frequency count (eliminates noise)
    counts = Counter({w: c for w, c in counts.items() if c >= min_count})

    items = counts.most_common()  # all words, sorted by frequency
    out = _DIR / "data" / f"spanish_{word_length}letter.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["word", "count"])
        for w, c in items:
            writer.writerow([w, c])

    print(f"\n  {word_length}-letter words: {openslr_total} in OpenSLR -> {len(items)} after Hunspell filter (min_count={min_count})")
    print(f"    {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and build clean Spanish word list for Wordle"
    )
    parser.add_argument("--length", type=int, default=5, help="Word length (default: 5)")
    parser.add_argument("--min-count", type=int, default=2,
                        help="Minimum frequency count to include a word (default: 2)")
    parser.add_argument("--all-lengths", action="store_true",
                        help="Download word lists for lengths 4, 5, and 6")
    args = parser.parse_args()

    # Download Hunspell dictionary
    print("Downloading Hunspell Spanish dictionary ...")
    hunspell_path = _CACHE / "spanish_words.txt"
    _download(HUNSPELL_URL, hunspell_path)
    hunspell_words = _load_hunspell(hunspell_path)

    if args.all_lengths:
        for length in [4, 5, 6]:
            print(f"\nBuilding {length}-letter Spanish word list ...\n")
            build_wordlist(word_length=length, hunspell_words=hunspell_words,
                           min_count=args.min_count)
    else:
        print(f"\nBuilding {args.length}-letter Spanish word list ...\n")
        build_wordlist(word_length=args.length, hunspell_words=hunspell_words,
                       min_count=args.min_count)
    print("\nDone.")


if __name__ == "__main__":
    main()
