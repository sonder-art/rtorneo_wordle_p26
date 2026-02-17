#!/usr/bin/env python3
"""One-command launcher: setup + tournament + dashboard.

Usage:
    # Quick test (mini corpus, 10 games)
    python3 run_all.py

    # Full official tournament (downloads data if missing)
    python3 run_all.py --num-games 100

    # Real evaluation tournament (all students, full corpus, shock)
    python3 run_all.py --real --num-games 500

    # Just setup (download data, no tournament)
    python3 run_all.py --setup-only

    # With dashboard (opens browser after tournament)
    python3 run_all.py --dashboard
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_DATA = _DIR / "data"


def _data_exists(word_length: int) -> bool:
    """Check if corpus for given word length exists."""
    csv_path = _DATA / f"spanish_{word_length}letter.csv"
    mini_path = _DATA / f"mini_spanish_{word_length}.txt"
    return csv_path.exists() or mini_path.exists()


def _all_data_exists() -> bool:
    return all(_data_exists(l) for l in [4, 5, 6])


def _run(cmd: list[str], check: bool = True) -> int:
    """Run a command, streaming output."""
    print(f"\n>>> {' '.join(cmd)}\n", flush=True)
    result = subprocess.run(cmd, cwd=str(_DIR))
    if check and result.returncode != 0:
        print(f"\nCommand failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-command Wordle tournament launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python3 run_all.py                          # quick test (mini corpus)
  python3 run_all.py --num-games 100          # official tournament, 100 games/round
  python3 run_all.py --real                   # class evaluation (all students, shock)
  python3 run_all.py --real --num-games 500   # class evaluation, 500 games/round
  python3 run_all.py --setup-only             # just download data
  python3 run_all.py --dashboard              # run tournament + open dashboard
""",
    )
    parser.add_argument("--num-games", type=int, default=None,
                        help="Games per round (default: 10 for quick, 100 for --real)")
    parser.add_argument("--real", action="store_true",
                        help="Real evaluation tournament: full corpus, 100 games, "
                             "3 repetitions, 5%% shock. Use this in class.")
    parser.add_argument("--setup-only", action="store_true",
                        help="Only download data, don't run tournament")
    parser.add_argument("--dashboard", action="store_true",
                        help="Launch dashboard after tournament (no Docker needed)")
    parser.add_argument("--dashboard-only", action="store_true",
                        help="Just launch the dashboard server (no tournament)")
    parser.add_argument("--download", action="store_true",
                        help="Force re-download of word lists")
    parser.add_argument("--repetitions", type=int, default=None,
                        help="Override number of repetitions (default: 1 normal, 3 for --real)")
    parser.add_argument("--shock", type=float, default=None,
                        help="Override shock scale (default: 0.0 normal, 0.05 for --real)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--team", type=str, default=None,
                        help="Only run this team + benchmarks")
    parser.add_argument("--corpus", choices=["mini", "full"], default=None,
                        help="Corpus size: mini (~50 words, fast debug) or full (~20k words) "
                             "(default: full)")
    args = parser.parse_args()

    # ── Step 1: Download data if missing ──────────────────────────
    if args.download or not _all_data_exists():
        print("=" * 60)
        print("  STEP 1: Downloading word lists")
        print("=" * 60, flush=True)
        _run([sys.executable, "download_words.py", "--all-lengths"])
    else:
        print("=" * 60)
        print("  STEP 1: Word lists OK (use --download to re-download)")
        print("=" * 60, flush=True)

    if args.setup_only:
        print("\nSetup complete. Ready to run tournaments.")
        return

    if args.dashboard_only:
        _launch_dashboard()
        return

    # ── Step 2: Run tournament ────────────────────────────────────
    print("\n" + "=" * 60)
    if args.real:
        print("  STEP 2: Running REAL evaluation tournament")
    else:
        print("  STEP 2: Running official tournament")
    print("=" * 60, flush=True)

    cmd = [sys.executable, "tournament.py", "--official"]

    if args.real:
        num_games = args.num_games or 100
        repetitions = args.repetitions if args.repetitions is not None else 3
        shock = args.shock if args.shock is not None else 0.05
    else:
        num_games = args.num_games or 10
        repetitions = args.repetitions if args.repetitions is not None else 1
        shock = args.shock if args.shock is not None else 0.0

    cmd += ["--num-games", str(num_games)]
    cmd += ["--repetitions", str(repetitions)]

    if shock > 0:
        cmd += ["--shock", str(shock)]

    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]

    if args.team:
        cmd += ["--team", args.team]

    corpus = args.corpus or "full"
    cmd += ["--corpus", corpus]

    # JSON output: team runs get explicit path, normal runs auto-generate
    # results/runs/<timestamp>/ directories (+ results/latest.json)
    if args.team:
        json_path = f"estudiantes/{args.team}/results/tournament_results.json"
        cmd += ["--json", json_path]

    _run(cmd)

    # ── Step 3: Dashboard (optional) ──────────────────────────────
    if args.dashboard:
        _launch_dashboard()
    else:
        print("\n" + "-" * 60)
        if args.team:
            print(f"  Results saved to: estudiantes/{args.team}/results/")
        else:
            print(f"  Results saved to: results/runs/ (+ results/latest.json)")
        print(f"  To view dashboard: python3 run_all.py --dashboard-only")
        print("-" * 60)


def _launch_dashboard() -> None:
    """Launch the Python-based dashboard server."""
    print("\n" + "=" * 60)
    print("  Launching dashboard")
    print("=" * 60)
    print("\nDashboard at http://localhost:8080")
    print("You can launch and manage tournaments from the browser.")
    print("Press Ctrl+C to stop.\n", flush=True)
    webbrowser.open("http://localhost:8080")
    _run([sys.executable, str(_DIR / "dashboard" / "server.py"), "--port", "8080"], check=False)


if __name__ == "__main__":
    main()
