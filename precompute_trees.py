#!/usr/bin/env python3
"""Precompute entropy-optimal decision trees for Wordle.

Builds one decision tree per config ({4,5,6} letters x {uniform,frequency}).
Uses all CPU cores. Fully resumable: checkpoint saved after each node.
Can be hard-stopped (Ctrl+C / kill) and restarted from where it left off.

Usage:
    python3 precompute_trees.py                     # all 6 configs
    python3 precompute_trees.py --length 5          # only 5-letter
    python3 precompute_trees.py --mode uniform      # only uniform
    python3 precompute_trees.py --corpus mini       # quick test with mini corpus
    python3 precompute_trees.py --max-depth 3       # shallower tree

    # Resume after interruption (automatic):
    python3 precompute_trees.py                     # picks up from checkpoint
"""

from __future__ import annotations

import argparse
import math
import os
import pickle
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))

from wordle_env import feedback
from lexicon import load_lexicon

TREE_DIR = _DIR / "data" / "trees"


# ── Checkpoint I/O ─────────────────────────────────────────

def save_checkpoint(data: dict, path: Path) -> None:
    """Atomically save checkpoint (write tmp then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_checkpoint(path: Path) -> dict:
    """Load checkpoint or return empty dict."""
    path = Path(path)
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return {}


# ── Worker functions (module-level for pickling) ───────────

def _eval_chunk(args):
    """Worker: evaluate entropy for a chunk of guesses against candidates."""
    chunk, candidates, weight_pairs = args
    weights = dict(weight_pairs)
    candidate_set = set(candidates)
    best_guess = None
    best_ent = -1.0
    best_is_cand = False

    for g in chunk:
        partition = defaultdict(float)
        for c in candidates:
            pat = feedback(c, g)
            partition[pat] += weights[c]

        total = sum(partition.values())
        ent = 0.0
        for v in partition.values():
            p = v / total
            if p > 0:
                ent -= p * math.log2(p)

        is_cand = g in candidate_set
        if best_guess is None or ent > best_ent or (
            ent == best_ent and is_cand and not best_is_cand
        ):
            best_ent = ent
            best_guess = g
            best_is_cand = is_cand

    return best_guess, best_ent, best_is_cand


def _compute_node(args):
    """Worker: compute best guess for a single tree node."""
    path, candidates, guess_pool, weight_pairs = args
    weights = dict(weight_pairs)
    candidate_set = set(candidates)
    best_guess = candidates[0]
    best_ent = -1.0
    best_is_cand = True

    for g in guess_pool:
        partition = defaultdict(float)
        for c in candidates:
            pat = feedback(c, g)
            partition[pat] += weights[c]

        total = sum(partition.values())
        ent = 0.0
        for v in partition.values():
            p = v / total
            if p > 0:
                ent -= p * math.log2(p)

        is_cand = g in candidate_set
        if ent > best_ent or (ent == best_ent and is_cand and not best_is_cand):
            best_ent = ent
            best_guess = g
            best_is_cand = is_cand

    return path, best_guess, best_ent


# ── Tree utilities ─────────────────────────────────────────

def get_children(candidates, guess):
    """Partition candidates by feedback pattern from guess."""
    children = defaultdict(list)
    for c in candidates:
        pat = feedback(c, guess)
        children[pat].append(c)
    return dict(children)


def build_pending(checkpoint, vocabulary, max_depth, min_candidates):
    """BFS walk of checkpoint tree to find all nodes still needing computation."""
    pending = []

    def visit(path, candidates):
        if len(candidates) <= 1:
            return
        if path not in checkpoint:
            pending.append((path, list(candidates)))
            return  # can't expand children without knowing this node's guess
        if len(path) >= max_depth:
            return
        guess = checkpoint[path]
        for pat, child_cands in get_children(candidates, guess).items():
            if len(child_cands) > min_candidates:
                visit(path + (pat,), child_cands)

    visit((), list(vocabulary))
    pending.sort(key=lambda x: (len(x[0]), x[0]))
    return pending


# ── Main tree builder ──────────────────────────────────────

def build_tree(
    vocabulary: list[str],
    weights: dict[str, float],
    wl: int,
    mode: str,
    max_depth: int = 4,
    min_candidates: int = 15,
    max_workers: int | None = None,
    checkpoint_path: str | Path | None = None,
) -> dict:
    """Build decision tree with parallel computation and per-node checkpointing."""
    if max_workers is None:
        max_workers = os.cpu_count() or 4

    checkpoint = load_checkpoint(checkpoint_path) if checkpoint_path else {}

    print(f"\n  Config: {wl}-letter {mode}")
    print(f"  Vocabulary: {len(vocabulary)} words")
    print(f"  Checkpoint: {len(checkpoint)} nodes already computed")
    print(f"  Max depth: {max_depth}, min candidates: {min_candidates}")
    print(f"  Workers: {max_workers}")

    total_start = time.time()

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        while True:
            pending = build_pending(checkpoint, vocabulary, max_depth, min_candidates)
            if not pending:
                break

            depth = len(pending[0][0])  # path length of first pending node
            level_nodes = [(p, c) for p, c in pending if len(p) == depth]

            print(f"\n  --- Depth {depth}: {len(level_nodes)} node(s) ---")

            if depth == 0 and len(level_nodes) == 1:
                _compute_root(level_nodes[0], vocabulary, weights,
                              executor, max_workers, checkpoint, checkpoint_path)
            else:
                _compute_level(level_nodes, weights, executor,
                               checkpoint, checkpoint_path)

    total_elapsed = time.time() - total_start
    print(f"\n  Tree complete: {len(checkpoint)} nodes in {total_elapsed:.0f}s")
    return checkpoint


def _compute_root(node, vocabulary, weights, executor, max_workers,
                  checkpoint, checkpoint_path):
    """Depth 0: single large node, parallelize by splitting guess pool."""
    path, candidates = node
    guess_pool = list(vocabulary)
    wp = list(weights.items())

    chunk_size = max(50, len(guess_pool) // (max_workers * 4))
    chunks = [guess_pool[i:i + chunk_size]
              for i in range(0, len(guess_pool), chunk_size)]

    print(f"  Evaluating {len(guess_pool)} guesses "
          f"x {len(candidates)} candidates "
          f"in {len(chunks)} chunks ...")

    t0 = time.time()
    best = (candidates[0], -1.0, True)
    done = 0

    futs = {executor.submit(_eval_chunk, (ch, candidates, wp)): i
            for i, ch in enumerate(chunks)}

    for fut in as_completed(futs):
        g, ent, is_cand = fut.result()
        done += 1
        if g and (ent > best[1] or
                  (ent == best[1] and is_cand and not best[2])):
            best = (g, ent, is_cand)
        elapsed = time.time() - t0
        eta = elapsed / done * (len(chunks) - done) if done else 0
        print(f"\r  [{done}/{len(chunks)}] "
              f"best={best[0]} H={best[1]:.4f}  "
              f"{elapsed:.0f}s elapsed  ETA {eta:.0f}s   ",
              end="", flush=True)

    checkpoint[path] = best[0]
    if checkpoint_path:
        save_checkpoint(checkpoint, checkpoint_path)
    elapsed = time.time() - t0
    print(f"\n  -> {best[0]} (H={best[1]:.4f}) [{elapsed:.0f}s]")


def _compute_level(level_nodes, weights, executor, checkpoint, checkpoint_path):
    """Depth 1+: parallelize across nodes."""
    t0 = time.time()
    done = 0

    futs = {}
    for path, candidates in level_nodes:
        wp = [(c, weights[c]) for c in candidates]
        fut = executor.submit(_compute_node, (path, candidates, candidates, wp))
        futs[fut] = (path, len(candidates))

    for fut in as_completed(futs):
        path, guess, ent = fut.result()
        n_cands = futs[fut][1]
        checkpoint[path] = guess
        done += 1

        if done % 10 == 0 or done == len(level_nodes):
            if checkpoint_path:
                save_checkpoint(checkpoint, checkpoint_path)

        elapsed = time.time() - t0
        print(f"\r  [{done}/{len(level_nodes)}] "
              f"cands={n_cands} -> {guess} H={ent:.3f}  "
              f"{elapsed:.0f}s",
              end="", flush=True)

    elapsed = time.time() - t0
    print(f"\n  Depth done: {len(level_nodes)} nodes in {elapsed:.0f}s")


# ── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Precompute entropy decision trees for Wordle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python3 precompute_trees.py                     # all 6 configs (full corpus)
  python3 precompute_trees.py --length 5          # only 5-letter words
  python3 precompute_trees.py --corpus mini       # quick test with mini corpus
  python3 precompute_trees.py --max-depth 3       # shallower trees (faster)

  # Resume after Ctrl+C (automatic):
  python3 precompute_trees.py                     # picks up from checkpoint
""")
    parser.add_argument("--length", type=int, nargs="+", default=[4, 5, 6],
                        help="Word lengths (default: 4 5 6)")
    parser.add_argument("--mode", nargs="+", default=["uniform", "frequency"],
                        choices=["uniform", "frequency"],
                        help="Modes (default: uniform frequency)")
    parser.add_argument("--max-depth", type=int, default=4,
                        help="Max tree depth (default: 4)")
    parser.add_argument("--min-candidates", type=int, default=15,
                        help="Stop expanding when candidates <= N (default: 15)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Parallel workers (default: all CPU cores)")
    parser.add_argument("--corpus", choices=["mini", "full"], default="full",
                        help="Corpus size (default: full)")
    args = parser.parse_args()

    TREE_DIR.mkdir(parents=True, exist_ok=True)

    configs = [(wl, m) for wl in args.length for m in args.mode]
    print(f"Precomputing {len(configs)} decision tree(s)")
    print(f"Output: {TREE_DIR}")

    for wl, mode in configs:
        data_dir = _DIR / "data"
        if args.corpus == "mini":
            words_path = str(data_dir / f"mini_spanish_{wl}.txt")
        else:
            words_path = str(data_dir / f"spanish_{wl}letter.csv")

        lex = load_lexicon(path=words_path, word_length=wl, mode=mode)

        if mode == "frequency":
            weights = dict(lex.probs)
        else:
            w = 1.0 / len(lex.words)
            weights = {word: w for word in lex.words}

        ckpt_path = TREE_DIR / f"checkpoint_{wl}_{mode}.pkl"
        tree_path = TREE_DIR / f"tree_{wl}_{mode}.pkl"

        print(f"\n{'=' * 60}")
        print(f"  {wl}-letter {mode} ({len(lex.words)} words)")
        print(f"{'=' * 60}")

        try:
            tree = build_tree(
                vocabulary=lex.words,
                weights=weights,
                wl=wl,
                mode=mode,
                max_depth=args.max_depth,
                min_candidates=args.min_candidates,
                max_workers=args.workers,
                checkpoint_path=ckpt_path,
            )
        except KeyboardInterrupt:
            print(f"\n\n  Interrupted! Checkpoint saved at {ckpt_path}")
            print(f"  Re-run to continue from where you left off.")
            sys.exit(0)

        # Save final tree and remove checkpoint
        save_checkpoint(tree, tree_path)
        print(f"  Final tree: {tree_path} ({len(tree)} nodes)")

        if ckpt_path.exists():
            ckpt_path.unlink()
            print(f"  Checkpoint removed (tree complete)")

    print(f"\nAll done! Trees in {TREE_DIR}")


if __name__ == "__main__":
    main()
