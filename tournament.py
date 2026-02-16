#!/usr/bin/env python3
"""Run all discovered strategies and compare them.

Features:
  - Auto-discovers built-in strategies AND student submissions.
  - Runs strategies in parallel (one process per strategy).
  - Supports two probability modes: ``uniform`` and ``frequency``.
  - Outputs summary table, CSV, and histogram.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time as _time_mod
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ------------------------------------------------------------------
# Result containers
# ------------------------------------------------------------------

@dataclass
class GameResult:
    strategy: str
    secret: str
    num_guesses: int
    solved: bool
    timed_out: bool = False


@dataclass
class TournamentResults:
    games: list[GameResult] = field(default_factory=list)

    def to_csv(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["strategy", "secret", "num_guesses", "solved"])
            for g in self.games:
                writer.writerow([g.strategy, g.secret, g.num_guesses, int(g.solved)])

    def print_summary(self) -> None:
        from collections import defaultdict

        by_strat: dict[str, list[GameResult]] = defaultdict(list)
        for g in self.games:
            by_strat[g.strategy].append(g)

        print(f"\n{'Strategy':<25} {'Games':>6} {'Solved':>7} {'Rate':>6} "
              f"{'Mean':>6} {'Median':>7} {'Max':>5}")
        print("-" * 72)
        # Sort by mean guesses (ascending = best first)
        ranking = sorted(by_strat.items(), key=lambda kv: sum(r.num_guesses for r in kv[1]) / len(kv[1]))
        for name, results in ranking:
            n = len(results)
            solved = sum(1 for r in results if r.solved)
            guesses = sorted(r.num_guesses for r in results)
            mean = sum(guesses) / n
            median = guesses[n // 2] if n % 2 == 1 else (
                guesses[n // 2 - 1] + guesses[n // 2]
            ) / 2
            mx = max(guesses)
            rate = 100 * solved / n
            print(f"{name:<25} {n:>6} {solved:>6}  {rate:>5.1f}% "
                  f"{mean:>6.2f} {median:>7.1f} {mx:>5}")
        print()

    def plot_histograms(self, path: str | Path | None = None) -> None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not installed — skipping plot", file=sys.stderr)
            return

        from collections import defaultdict

        by_strat: dict[str, list[int]] = defaultdict(list)
        for g in self.games:
            by_strat[g.strategy].append(g.num_guesses)

        strats = sorted(by_strat.keys())
        n_strats = len(strats)
        if n_strats == 0:
            return

        cols = min(n_strats, 4)
        rows = (n_strats + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows), squeeze=False)
        max_guess = max(g.num_guesses for g in self.games)
        bins = list(range(1, max_guess + 2))

        for idx, name in enumerate(strats):
            ax = axes[idx // cols][idx % cols]
            ax.hist(by_strat[name], bins=bins, edgecolor="black", align="left")
            ax.set_title(name, fontsize=10)
            ax.set_xlabel("Guesses")
            ax.set_ylabel("Count")

        # Hide unused axes
        for idx in range(n_strats, rows * cols):
            axes[idx // cols][idx % cols].set_visible(False)

        fig.suptitle("Guess-count distribution by strategy")
        fig.tight_layout()
        dest = Path(path) if path else RESULTS_DIR / "tournament_histograms.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(dest, dpi=150)
        plt.close(fig)
        print(f"Histogram saved to {dest}")

    def to_json(self, path: str | Path) -> None:
        """Write results as JSON for dashboard consumption."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "games": [asdict(g) for g in self.games],
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------
# Worker function (runs in a child process)
# ------------------------------------------------------------------

def _apply_resource_limits(memory_mb: int = 2048) -> None:
    """Set resource limits for the worker process: 1 CPU core, memory cap."""
    import os
    import resource as _resource

    # Pin to a single CPU core
    try:
        available = os.sched_getaffinity(0)
        if len(available) > 1:
            # Pick one core deterministically
            os.sched_setaffinity(0, {min(available)})
    except (AttributeError, OSError):
        pass  # Not available on this platform

    # Set memory limit (virtual memory)
    mem_bytes = memory_mb * 1024 * 1024
    try:
        _resource.setrlimit(_resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (ValueError, OSError):
        # Fallback: try data segment limit
        try:
            _resource.setrlimit(_resource.RLIMIT_DATA, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass


def _run_strategy_worker(
    strat_cls_info: tuple[str, str],
    vocabulary: list[str],
    secrets: list[str],
    word_length: int,
    max_guesses: int,
    allow_non_words: bool,
    mode: str = "uniform",
    probabilities: dict[str, float] | None = None,
    game_timeout: float = 5.0,
    memory_limit_mb: int = 2048,
) -> list[GameResult]:
    """Run a single strategy against all secrets. Executed in a subprocess."""
    import importlib
    import importlib.util
    import os
    import sys as _sys
    import time as _time
    from pathlib import Path as _Path

    # Apply resource limits
    _apply_resource_limits(memory_limit_mb)

    # Verify single-core enforcement
    try:
        cores = os.sched_getaffinity(0)
        if len(cores) > 1:
            print(f"  [WARN] Strategy worker using {len(cores)} CPU cores "
                  f"(expected 1)", file=_sys.stderr, flush=True)
    except (AttributeError, OSError):
        pass

    if probabilities is None:
        p = 1.0 / len(vocabulary) if vocabulary else 0.0
        probabilities = {w: p for w in vocabulary}

    code_dir = str(_Path(__file__).resolve().parent)
    if code_dir not in _sys.path:
        _sys.path.insert(0, code_dir)

    from strategy import Strategy as _Strategy, GameConfig
    from wordle_env import WordleEnv

    source, cls_name = strat_cls_info

    if source == "__builtin__":
        from strategies import _discover_builtin
        for cls in _discover_builtin():
            if cls.__name__ == cls_name:
                break
        else:
            raise RuntimeError(f"Built-in strategy class {cls_name} not found")
    else:
        spec = importlib.util.spec_from_file_location(f"_worker_{cls_name}", source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {source}")
        mod = importlib.util.module_from_spec(spec)
        _sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        cls = None
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and issubclass(obj, _Strategy) and obj is not _Strategy and obj.__name__ == cls_name:
                cls = obj
                break
        if cls is None:
            raise RuntimeError(f"Class {cls_name} not found in {source}")

    strat = cls()
    env = WordleEnv(
        vocabulary=vocabulary,
        word_length=word_length,
        max_guesses=max_guesses,
        allow_non_words=allow_non_words,
    )

    config = GameConfig(
        word_length=word_length,
        vocabulary=tuple(vocabulary),
        mode=mode,
        probabilities=probabilities,
        max_guesses=max_guesses,
        allow_non_words=allow_non_words,
    )

    # Strict timeout enforcement via SIGALRM
    import signal as _signal

    class _GameTimeout(Exception):
        pass

    def _alarm_handler(signum, frame):
        raise _GameTimeout()

    _signal.signal(_signal.SIGALRM, _alarm_handler)

    results: list[GameResult] = []
    timeout_secs = max(1, int(game_timeout))

    for secret in secrets:
        env.reset(secret=secret)
        timed_out = False
        _signal.alarm(timeout_secs)  # Hard timeout — kills mid-computation
        try:
            strat.begin_game(config)
            while not env.game_over():
                word = strat.guess(env.history)
                env.guess(word)
        except _GameTimeout:
            timed_out = True
        finally:
            _signal.alarm(0)  # Cancel alarm

        if not timed_out:
            strat.end_game(secret, env.is_solved(), len(env.history))
        results.append(GameResult(
            strategy=strat.name,
            secret=secret,
            num_guesses=len(env.history) if not timed_out else max_guesses + 1,
            solved=env.is_solved() if not timed_out else False,
            timed_out=timed_out,
        ))

    return results


# ------------------------------------------------------------------
# Tournament runner
# ------------------------------------------------------------------

def run_tournament(
    vocabulary: list[str],
    secrets: list[str] | None = None,
    word_length: int = 5,
    max_guesses: int = 6,
    num_games: int | None = None,
    seed: int = 42,
    allow_non_words: bool = True,
    max_workers: int | None = None,
    mode: str = "uniform",
    probabilities: dict[str, float] | None = None,
    game_timeout: float = 5.0,
    team_filter: str | None = None,
) -> TournamentResults:
    from strategies import _discover_builtin, _discover_students

    rng = random.Random(seed)
    if secrets is None:
        secrets = list(vocabulary)
    if num_games is not None and num_games < len(secrets):
        secrets = rng.sample(secrets, num_games)

    if probabilities is None:
        p = 1.0 / len(vocabulary) if vocabulary else 0.0
        probabilities = {w: p for w in vocabulary}

    # Prepare strategy descriptors for workers
    strat_infos: list[tuple[tuple[str, str], str]] = []

    for cls in _discover_builtin():
        inst = cls()
        strat_infos.append((("__builtin__", cls.__name__), inst.name))

    for cls in _discover_students(team_filter=team_filter):
        inst = cls()
        src_file = sys.modules.get(cls.__module__)
        if src_file and hasattr(src_file, "__file__") and src_file.__file__:
            strat_infos.append(((src_file.__file__, cls.__name__), inst.name))
        else:
            strat_infos.append((("__builtin__", cls.__name__), inst.name))

    if not strat_infos:
        print("No strategies found.", file=sys.stderr)
        return TournamentResults()

    # Default: batch strategies to avoid overloading the system
    import os as _os
    if max_workers is None:
        max_workers = min(len(strat_infos), _os.cpu_count() or 4, 4)

    print(f"Running {len(strat_infos)} strategies on {len(secrets)} words "
          f"(workers: {max_workers}, "
          f"timeout: {game_timeout}s/game, "
          f"memory: 2GB/strategy) ...", flush=True)

    results = TournamentResults()

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for info, display_name in strat_infos:
            fut = executor.submit(
                _run_strategy_worker,
                info,
                vocabulary,
                secrets,
                word_length,
                max_guesses,
                allow_non_words,
                mode,
                probabilities,
                game_timeout,
            )
            futures[fut] = display_name

        for fut in as_completed(futures):
            name = futures[fut]
            try:
                game_results = fut.result()
                results.games.extend(game_results)
                solved = sum(1 for g in game_results if g.solved)
                touts = sum(1 for g in game_results if g.timed_out)
                mean = sum(g.num_guesses for g in game_results) / len(game_results)
                extra = f", timeouts: {touts}" if touts else ""
                print(f"  {name:<25} done — {solved}/{len(game_results)} solved, "
                      f"mean {mean:.2f}{extra}")
            except Exception as exc:
                print(f"  {name:<25} FAILED: {exc}", file=sys.stderr)

    return results


# ------------------------------------------------------------------
# Canonical tournament rounds
# ------------------------------------------------------------------

CANONICAL_ROUNDS = [
    {"word_length": 4, "mode": "uniform"},
    {"word_length": 4, "mode": "frequency"},
    {"word_length": 5, "mode": "uniform"},
    {"word_length": 5, "mode": "frequency"},
    {"word_length": 6, "mode": "uniform"},
    {"word_length": 6, "mode": "frequency"},
]


# ------------------------------------------------------------------
# Leaderboard computation
# ------------------------------------------------------------------

def _compute_round_summary(
    games: list[GameResult],
) -> dict[str, dict]:
    """Aggregate per-strategy stats from a list of GameResult."""
    from collections import defaultdict

    by_strat: dict[str, list[GameResult]] = defaultdict(list)
    for g in games:
        by_strat[g.strategy].append(g)

    summaries = {}
    for name, results in by_strat.items():
        n = len(results)
        solved = sum(1 for r in results if r.solved)
        touts = sum(1 for r in results if r.timed_out)
        guesses = sorted(r.num_guesses for r in results)
        mean_g = sum(guesses) / n if n else 0
        median_g = guesses[n // 2] if n % 2 == 1 else (
            guesses[n // 2 - 1] + guesses[n // 2]) / 2 if n else 0
        # Guess distribution
        dist: dict[str, int] = {}
        for r in results:
            if r.solved:
                dist[str(r.num_guesses)] = dist.get(str(r.num_guesses), 0) + 1
            else:
                dist["failed"] = dist.get("failed", 0) + 1
        summaries[name] = {
            "name": name,
            "games_played": n,
            "games_solved": solved,
            "solve_rate": round(solved / n, 4) if n else 0,
            "mean_guesses": round(mean_g, 3),
            "median_guesses": median_g,
            "max_guesses": max(guesses) if guesses else 0,
            "timed_out": touts,
            "guess_distribution": dist,
        }
    return summaries


def compute_leaderboard(
    round_results: list[dict],
) -> list[dict]:
    """Compute leaderboard from round summaries.

    Scoring: per round, rank strategies by mean_guesses (ascending).
    1st place gets N points (N = num strategies), 2nd gets N-1, etc.
    Ties get averaged points. Sum across all rounds.
    """
    from collections import defaultdict

    total_points: dict[str, float] = defaultdict(float)
    round_points: dict[str, dict[str, float]] = defaultdict(dict)
    all_solve_rates: dict[str, list[float]] = defaultdict(list)
    all_mean_guesses: dict[str, list[float]] = defaultdict(list)

    for rd in round_results:
        round_id = rd["round_id"]
        strats = rd["strategies"]
        n = len(strats)
        # Sort by mean guesses ascending (best first)
        ranked = sorted(strats, key=lambda s: s["mean_guesses"])

        # Assign points with tie handling
        i = 0
        while i < len(ranked):
            j = i
            while j < len(ranked) and ranked[j]["mean_guesses"] == ranked[i]["mean_guesses"]:
                j += 1
            # Positions i..j-1 are tied
            avg_pts = sum(n - k for k in range(i, j)) / (j - i)
            for k in range(i, j):
                s_name = ranked[k]["name"]
                total_points[s_name] += avg_pts
                round_points[s_name][round_id] = avg_pts
            i = j

        for s in strats:
            all_solve_rates[s["name"]].append(s["solve_rate"])
            all_mean_guesses[s["name"]].append(s["mean_guesses"])

    # Build sorted leaderboard
    entries = []
    for name in total_points:
        entries.append({
            "strategy": name,
            "total_points": round(total_points[name], 2),
            "round_points": round_points[name],
            "overall_solve_rate": round(
                sum(all_solve_rates[name]) / len(all_solve_rates[name]), 4
            ) if all_solve_rates[name] else 0,
            "overall_mean_guesses": round(
                sum(all_mean_guesses[name]) / len(all_mean_guesses[name]), 3
            ) if all_mean_guesses[name] else 0,
        })
    entries.sort(key=lambda e: -e["total_points"])
    for rank, e in enumerate(entries, 1):
        e["rank"] = rank
    return entries


def print_leaderboard(entries: list[dict]) -> None:
    """Print a nicely formatted leaderboard table."""
    print(f"\n{'='*72}")
    print(f"  LEADERBOARD")
    print(f"{'='*72}")
    print(f"  {'Rank':<6}{'Strategy':<25}{'Points':>8}{'Solve%':>8}{'MeanG':>8}")
    print(f"  {'-'*55}")
    for e in entries:
        print(f"  {e['rank']:<6}{e['strategy']:<25}"
              f"{e['total_points']:>8.1f}"
              f"{e['overall_solve_rate']*100:>7.1f}%"
              f"{e['overall_mean_guesses']:>8.2f}")
    print()


# ------------------------------------------------------------------
# Full tournament JSON export
# ------------------------------------------------------------------

def build_tournament_json(
    round_results: list[dict],
    leaderboard: list[dict],
    config: dict,
) -> dict:
    """Build the complete tournament JSON for dashboard consumption."""
    tid = config.get("tournament_id", "tournament")
    return {
        "tournament_id": tid,
        "run_id": tid,
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "rounds": round_results,
        "leaderboard": leaderboard,
    }


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wordle strategy tournament",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python tournament.py                                    # mini lexicon, uniform
  python tournament.py --mode frequency                   # frequency-weighted
  python tournament.py --mode both                        # run both modes
  python tournament.py --official                         # 6 canonical rounds
  python tournament.py --official --repetitions 5         # 5 repetitions of 6 rounds
  python tournament.py --official --shock 0.05            # with distribution perturbation
  python tournament.py --team my_team --num-games 20      # local team tournament
  python tournament.py --words data/spanish_5letter.csv   # big downloaded list
  python tournament.py --num-games 100                    # subsample 100 secrets
""",
    )
    parser.add_argument("--words", type=str, default=None, help="Path to word list (.txt or .csv)")
    parser.add_argument("--length", type=int, default=5, help="Word length (default: 5)")
    parser.add_argument("--max-guesses", type=int, default=6, help="Max guesses per game (default: 6)")
    parser.add_argument("--num-games", type=int, default=None, help="Limit number of secret words to test")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed (default: random for official, 42 otherwise)")
    parser.add_argument("--vocab-only", action="store_true",
                        help="Restrict guesses to vocabulary words only "
                             "(default: any letter combination allowed)")
    parser.add_argument("--mode", choices=["uniform", "frequency", "both"], default="uniform",
                        help="Probability mode (default: uniform)")
    parser.add_argument("--workers", type=int, default=None, help="Max parallel workers (default: auto)")
    parser.add_argument("--csv", type=str, default=None, help="Save results CSV path")
    parser.add_argument("--plot", type=str, default=None, help="Save histogram path")
    parser.add_argument("--json", type=str, default=None, help="Save results JSON path")
    parser.add_argument("--official", action="store_true",
                        help="Run all 6 canonical rounds ({4,5,6} x {uniform,frequency})")
    parser.add_argument("--repetitions", type=int, default=1,
                        help="Number of repetitions for official tournament (default: 1)")
    parser.add_argument("--team", type=str, default=None,
                        help="Run only this team's strategy (+ benchmarks). "
                             "Results saved to estudiantes/<team>/results/")
    parser.add_argument("--game-timeout", type=float, default=5.0,
                        help="Max seconds per game (default: 5.0)")
    parser.add_argument("--shock", type=float, default=0.0,
                        help="Noise scale for frequency distribution perturbation "
                             "(0.0 = none, 0.05 = 5%%)")
    parser.add_argument("--name", type=str, default=None,
                        help="Optional human-readable tournament name")
    args = parser.parse_args()

    from lexicon import load_lexicon, perturb_probabilities

    # Determine output directory
    if args.team:
        out_dir = Path(__file__).resolve().parent / "estudiantes" / args.team / "results"
    else:
        out_dir = RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.official:
        _run_official(args, out_dir)
    else:
        _run_custom(args, out_dir)


def _run_custom(args, out_dir: Path) -> None:
    """Run a custom (non-official) tournament with user-specified parameters."""
    from lexicon import load_lexicon, perturb_probabilities

    modes = ["uniform", "frequency"] if args.mode == "both" else [args.mode]
    seed = args.seed if args.seed is not None else 42

    all_results = TournamentResults()
    round_summaries: list[dict] = []

    for mode in modes:
        print(f"\n{'='*60}")
        print(f"  MODE: {mode}  |  LENGTH: {args.length}")
        print(f"{'='*60}\n")

        lex = load_lexicon(path=args.words, word_length=args.length, mode=mode)
        probs = dict(lex.probs)
        if args.shock > 0 and mode == "frequency":
            probs = perturb_probabilities(probs, noise_scale=args.shock, seed=seed)
        print(f"Vocabulary: {len(lex.words)} words of length {args.length} (mode: {lex.mode})")

        t0 = _time_mod.time()
        results = run_tournament(
            vocabulary=lex.words,
            word_length=args.length,
            max_guesses=args.max_guesses,
            num_games=args.num_games,
            seed=seed,
            allow_non_words=not args.vocab_only,
            max_workers=args.workers,
            mode=mode,
            probabilities=probs,
            game_timeout=args.game_timeout,
            team_filter=args.team,
        )
        elapsed = _time_mod.time() - t0

        results.print_summary()
        print(f"Elapsed: {elapsed:.1f}s")
        all_results.games.extend(results.games)

        round_id = f"{args.length}_{mode}"
        summary = _compute_round_summary(results.games)
        round_summaries.append({
            "round_id": round_id,
            "word_length": args.length,
            "mode": mode,
            "num_games": len(set(g.secret for g in results.games)),
            "strategies": list(summary.values()),
        })

        suffix = f"_{mode}" if len(modes) > 1 else ""
        csv_path = args.csv or str(out_dir / f"tournament{suffix}.csv")
        results.to_csv(csv_path)
        print(f"CSV saved to {csv_path}")

        plot_path = args.plot or str(out_dir / f"tournament{suffix}.png")
        results.plot_histograms(plot_path)

    # Leaderboard and JSON if multiple modes
    if len(round_summaries) > 1:
        leaderboard = compute_leaderboard(round_summaries)
        print_leaderboard(leaderboard)

    if args.json:
        config = {
            "word_length": args.length,
            "modes": [m for m in (["uniform", "frequency"] if args.mode == "both" else [args.mode])],
            "shock_scale": args.shock,
            "game_timeout": args.game_timeout,
        }
        leaderboard = compute_leaderboard(round_summaries) if round_summaries else []
        data = build_tournament_json(round_summaries, leaderboard, config)
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON saved to {json_path}")


def _run_official(args, out_dir: Path) -> None:
    """Run the official tournament: 6 canonical rounds x N repetitions."""
    from lexicon import load_lexicon, perturb_probabilities

    master_seed = args.seed if args.seed is not None else random.randint(0, 2**31)
    rng = random.Random(master_seed)

    all_round_summaries: list[dict] = []
    all_results = TournamentResults()

    print(f"\n{'#'*60}")
    print(f"  OFFICIAL TOURNAMENT")
    print(f"  Rounds: {len(CANONICAL_ROUNDS)} configs x {args.repetitions} repetition(s)")
    print(f"  Timeout: {args.game_timeout}s/game | Shock: {args.shock}")
    print(f"{'#'*60}")

    for rep in range(1, args.repetitions + 1):
        if args.repetitions > 1:
            print(f"\n{'*'*60}")
            print(f"  REPETITION {rep}/{args.repetitions}")
            print(f"{'*'*60}")

        for rd in CANONICAL_ROUNDS:
            wl = rd["word_length"]
            mode = rd["mode"]
            round_seed = rng.randint(0, 2**31)

            print(f"\n{'='*60}")
            print(f"  ROUND: {wl}-letter {mode}"
                  + (f"  (rep {rep})" if args.repetitions > 1 else ""))
            print(f"{'='*60}\n")

            lex = load_lexicon(path=args.words, word_length=wl, mode=mode)
            probs = dict(lex.probs)
            if args.shock > 0 and mode == "frequency":
                probs = perturb_probabilities(probs, noise_scale=args.shock, seed=round_seed)
            print(f"Vocabulary: {len(lex.words)} words of length {wl} (mode: {mode})")

            t0 = _time_mod.time()
            results = run_tournament(
                vocabulary=lex.words,
                word_length=wl,
                max_guesses=args.max_guesses,
                num_games=args.num_games,
                seed=round_seed,
                allow_non_words=not args.vocab_only,
                max_workers=args.workers,
                mode=mode,
                probabilities=probs,
                game_timeout=args.game_timeout,
                team_filter=args.team,
            )
            elapsed = _time_mod.time() - t0
            results.print_summary()
            print(f"Elapsed: {elapsed:.1f}s")

            all_results.games.extend(results.games)

            round_id = f"{wl}_{mode}" + (f"_r{rep}" if args.repetitions > 1 else "")
            summary = _compute_round_summary(results.games)
            all_round_summaries.append({
                "round_id": round_id,
                "word_length": wl,
                "mode": mode,
                "repetition": rep,
                "seed": round_seed,
                "num_games": len(set(g.secret for g in results.games)),
                "strategies": list(summary.values()),
            })

    # Leaderboard
    leaderboard = compute_leaderboard(all_round_summaries)
    print_leaderboard(leaderboard)

    # Save outputs
    csv_path = args.csv or str(out_dir / "tournament_official.csv")
    all_results.to_csv(csv_path)
    print(f"CSV saved to {csv_path}")

    plot_path = args.plot or str(out_dir / "tournament_official.png")
    all_results.plot_histograms(plot_path)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.json:
        json_path = args.json
    else:
        run_dir = out_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        json_path = str(run_dir / "tournament_results.json")

    config = {
        "tournament_id": run_id,
        "name": args.name,
        "master_seed": master_seed,
        "num_games": args.num_games,
        "repetitions": args.repetitions,
        "shock_scale": args.shock,
        "game_timeout": args.game_timeout,
        "max_guesses": args.max_guesses,
        "rounds": [{"word_length": r["word_length"], "mode": r["mode"]} for r in CANONICAL_ROUNDS],
    }
    data = build_tournament_json(all_round_summaries, leaderboard, config)
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    json_content = json.dumps(data, indent=2, ensure_ascii=False)
    Path(json_path).write_text(json_content, encoding="utf-8")
    print(f"JSON saved to {json_path}")

    # Also write latest.json for backwards compat / dashboard default
    latest_path = out_dir / "latest.json"
    latest_path.write_text(json_content, encoding="utf-8")
    print(f"Latest copy: {latest_path}")


if __name__ == "__main__":
    main()
