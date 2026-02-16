#!/usr/bin/env python3
"""
Download and prepare a large Spanish word list for the Wordle tournament.

Source: OpenSLR SLR21 (CC BY-SA 3.0) — Spanish word frequencies.

Usage:
    python download_words.py                 # default: 5-letter words
    python download_words.py --length 6      # 6-letter words
    python download_words.py --limit 5000    # keep top-5000 by frequency
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


def _normalize(token: str) -> str:
    token = token.strip().lower()
    nfkd = unicodedata.normalize("NFKD", token)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


# ------------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------------

def build_wordlist(word_length: int = 5, limit: int = 20_000) -> Path:
    """Download OpenSLR data and produce ``data/spanish_{L}letter.csv``."""
    tgz_path = _CACHE / "es_wordlist.json.tgz"
    json_path = _CACHE / "es_wordlist.json"

    if not json_path.exists():
        _download(OPENSLR_URL, tgz_path)
        json_path = _extract_json(tgz_path)
    else:
        print(f"  (cached) {json_path.name}")

    print(f"  Parsing {json_path.name} ...")
    data: dict = json.loads(json_path.read_text(encoding="utf-8"))

    pattern = re.compile(rf"^[a-z]{{{word_length}}}$")
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

    items = counts.most_common(limit)
    out = _DIR / "data" / f"spanish_{word_length}letter.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["word", "count"])
        for w, c in items:
            writer.writerow([w, c])

    # Also write a plain txt (one word per line) for simple loading
    txt_out = _DIR / "data" / f"spanish_{word_length}letter.txt"
    txt_out.write_text("\n".join(w for w, _ in items) + "\n", encoding="utf-8")

    print(f"\n  Wrote {len(items)} words:")
    print(f"    {out}")
    print(f"    {txt_out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Spanish word list for Wordle")
    parser.add_argument("--length", type=int, default=5, help="Word length (default: 5)")
    parser.add_argument("--limit", type=int, default=20_000, help="Max words to keep (default: 20000)")
    parser.add_argument("--all-lengths", action="store_true",
                        help="Download word lists for lengths 4, 5, and 6")
    args = parser.parse_args()

    if args.all_lengths:
        for length in [4, 5, 6]:
            print(f"\nBuilding {length}-letter Spanish word list (top {args.limit}) ...\n")
            build_wordlist(word_length=length, limit=args.limit)
    else:
        print(f"Building {args.length}-letter Spanish word list (top {args.limit}) ...\n")
        build_wordlist(word_length=args.length, limit=args.limit)
    print("\nDone.")


if __name__ == "__main__":
    main()
