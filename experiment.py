#!/usr/bin/env python3
"""Run a single strategy with detailed per-game output."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

from lexicon import load_lexicon
from strategy import Strategy, GameConfig
from strategies import discover_strategies
from wordle_env import WordleEnv, filter_candidates

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _entropy_bits(n: int) -> float:
    return math.log2(n) if n > 1 else 0.0


def _find_strategy(name: str, team: str | None = None) -> type[Strategy]:
    if team:
        from strategies import _discover_builtin, _discover_students
        classes = _discover_builtin() + _discover_students(team_filter=team)
    else:
        classes = discover_strategies()
    for cls in classes:
        if cls().name.lower() == name.lower():
            return cls
    available = [cls().name for cls in classes]
    print(f"Strategy '{name}' not found. Available: {available}", file=sys.stderr)
    sys.exit(1)


def run_experiment(
    strat: Strategy,
    vocabulary: list[str],
    word_length: int = 5,
    max_guesses: int = 6,
    num_games: int = 10,
    seed: int = 42,
    allow_non_words: bool = True,
    verbose: bool = False,
    mode: str = "uniform",
    probabilities: dict[str, float] | None = None,
) -> list[dict]:
    rng = random.Random(seed)
    secrets = rng.sample(vocabulary, min(num_games, len(vocabulary)))

    if probabilities is None:
        p = 1.0 / len(vocabulary) if vocabulary else 0.0
        probabilities = {w: p for w in vocabulary}

    config = GameConfig(
        word_length=word_length,
        vocabulary=tuple(vocabulary),
        mode=mode,
        probabilities=probabilities,
        max_guesses=max_guesses,
        allow_non_words=allow_non_words,
    )

    env = WordleEnv(
        vocabulary=vocabulary,
        word_length=word_length,
        max_guesses=max_guesses,
        allow_non_words=allow_non_words,
    )

    logs: list[dict] = []

    for i, secret in enumerate(secrets, 1):
        env.reset(secret=secret)
        strat.begin_game(config)

        candidates = list(vocabulary)
        game_log: list[dict] = []

        if verbose:
            print(f"\n--- Game {i}/{len(secrets)} | Secret: {secret} ---")

        while not env.game_over():
            word = strat.guess(env.history)
            pat = env.guess(word)
            candidates = filter_candidates(candidates, word, pat)
            ent = _entropy_bits(len(candidates))

            step = {
                "guess": word,
                "feedback": list(pat),
                "remaining": len(candidates),
                "entropy_bits": round(ent, 3),
            }
            game_log.append(step)

            if verbose:
                pat_str = "".join(
                    {2: "\u2705", 1: "\U0001f7e8", 0: "\u2b1b"}[c] for c in pat
                )
                print(
                    f"  Guess {len(game_log)}: {word}  {pat_str}  "
                    f"remaining={len(candidates)}  H={ent:.2f} bits"
                )

        strat.end_game(secret, env.is_solved(), len(env.history))
        result = {
            "game": i,
            "secret": secret,
            "solved": env.is_solved(),
            "num_guesses": len(env.history),
            "steps": game_log,
        }
        logs.append(result)

        if verbose:
            status = "SOLVED" if env.is_solved() else "FAILED"
            print(f"  -> {status} in {len(env.history)} guesses")

    return logs


def print_experiment_summary(logs: list[dict], strategy_name: str) -> None:
    n = len(logs)
    solved = sum(1 for g in logs if g["solved"])
    guesses = [g["num_guesses"] for g in logs]
    mean = sum(guesses) / n if n else 0
    guesses_sorted = sorted(guesses)
    median = (
        guesses_sorted[n // 2]
        if n % 2 == 1
        else (guesses_sorted[n // 2 - 1] + guesses_sorted[n // 2]) / 2
    )
    print(f"\n=== {strategy_name} — {n} games ===")
    print(f"  Solved: {solved}/{n} ({100 * solved / n:.1f}%)")
    print(f"  Guesses — mean: {mean:.2f}, median: {median:.1f}, max: {max(guesses)}")


def plot_distribution(logs: list[dict], strategy_name: str, path: Path | None = None) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plot", file=sys.stderr)
        return

    guesses = [g["num_guesses"] for g in logs]
    mx = max(guesses) if guesses else 6
    bins = list(range(1, mx + 2))

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(guesses, bins=bins, edgecolor="black", align="left")
    ax.set_title(f"{strategy_name} — guess distribution")
    ax.set_xlabel("Guesses")
    ax.set_ylabel("Count")
    fig.tight_layout()

    dest = path or RESULTS_DIR / f"experiment_{strategy_name.lower()}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=150)
    plt.close(fig)
    print(f"Plot saved to {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-strategy Wordle experiment")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy name")
    parser.add_argument("--words", type=str, default=None, help="Path to word list")
    parser.add_argument("--length", type=int, default=5, help="Word length")
    parser.add_argument("--max-guesses", type=int, default=6, help="Max guesses per game")
    parser.add_argument("--num-games", type=int, default=10, help="Number of games")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--mode", choices=["uniform", "frequency"], default="uniform",
                        help="Probability mode (default: uniform)")
    parser.add_argument("--vocab-only", action="store_true",
                        help="Restrict guesses to vocabulary words only "
                             "(default: any letter combination allowed)")
    parser.add_argument("--verbose", action="store_true", help="Print per-game details")
    parser.add_argument("--plot", type=str, default=None, help="Save plot to this path")
    parser.add_argument("--json", type=str, default=None, help="Save results as JSON")
    parser.add_argument("--team", type=str, default=None,
                        help="Team name (resolves strategy from team dir, "
                             "saves outputs to estudiantes/<team>/results/)")
    args = parser.parse_args()

    # Determine output directory
    if args.team:
        out_dir = Path(__file__).resolve().parent / "estudiantes" / args.team / "results"
    else:
        out_dir = RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    lex = load_lexicon(path=args.words, word_length=args.length, mode=args.mode)
    print(f"Vocabulary: {len(lex.words)} words of length {args.length} (mode: {lex.mode})")

    cls = _find_strategy(args.strategy, team=args.team)
    strat = cls()
    print(f"Strategy: {strat.name}")

    logs = run_experiment(
        strat=strat,
        vocabulary=lex.words,
        word_length=args.length,
        max_guesses=args.max_guesses,
        num_games=args.num_games,
        seed=args.seed,
        allow_non_words=not args.vocab_only,
        verbose=args.verbose,
        mode=args.mode,
        probabilities=dict(lex.probs),
    )

    print_experiment_summary(logs, strat.name)

    plot_path = Path(args.plot) if args.plot else out_dir / f"experiment_{strat.name.lower()}.png"
    plot_distribution(logs, strat.name, plot_path)

    # JSON output
    if args.json:
        json_path = Path(args.json)
    else:
        json_path = out_dir / f"experiment_{strat.name.lower()}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "strategy": strat.name,
        "config": {
            "word_length": args.length,
            "mode": args.mode,
            "max_guesses": args.max_guesses,
            "num_games": args.num_games,
            "seed": args.seed,
        },
        "summary": {
            "games": len(logs),
            "solved": sum(1 for g in logs if g["solved"]),
            "solve_rate": round(sum(1 for g in logs if g["solved"]) / len(logs), 4) if logs else 0,
            "mean_guesses": round(sum(g["num_guesses"] for g in logs) / len(logs), 3) if logs else 0,
        },
        "games": logs,
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON saved to {json_path}")


if __name__ == "__main__":
    main()
