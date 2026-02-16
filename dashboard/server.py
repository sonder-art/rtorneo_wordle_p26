#!/usr/bin/env python3
"""Lightweight dashboard server with tournament management API.

Serves the static dashboard files and provides API endpoints
to launch and monitor tournaments. No external dependencies.

Usage:
    python3 dashboard/server.py                    # default port 8080
    python3 dashboard/server.py --port 9000        # custom port
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DASHBOARD_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _REPO_ROOT / "results"
_RUNS_DIR = _RESULTS_DIR / "runs"

# ── Tournament process state ────────────────────────────────

_lock = threading.Lock()
_process: subprocess.Popen | None = None
_status: dict = {"state": "idle", "started_at": None, "config": None,
                 "output_lines": [], "run_id": None}


def _is_running() -> bool:
    with _lock:
        if _process is not None and _process.poll() is None:
            return True
        return False


def _read_output(proc: subprocess.Popen) -> None:
    """Background thread: read subprocess stdout line by line."""
    for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip()
        with _lock:
            _status["output_lines"].append(line)
            if len(_status["output_lines"]) > 500:
                _status["output_lines"] = _status["output_lines"][-500:]
    proc.wait()
    with _lock:
        _status["state"] = "finished"
        _status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _status["exit_code"] = proc.returncode


def _launch_tournament(config: dict) -> dict:
    global _process, _status

    if _is_running():
        return {"error": "Tournament already running"}

    # Generate run ID
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    cmd = [sys.executable, str(_REPO_ROOT / "tournament.py"), "--official"]

    num_games = config.get("num_games", 100)
    cmd += ["--num-games", str(num_games)]

    repetitions = config.get("repetitions", 1)
    cmd += ["--repetitions", str(repetitions)]

    shock = config.get("shock", 0.0)
    if shock > 0:
        cmd += ["--shock", str(shock)]

    seed = config.get("seed")
    if seed is not None:
        cmd += ["--seed", str(seed)]

    team = config.get("team")
    if team:
        cmd += ["--team", str(team)]

    name = config.get("name")
    if name:
        cmd += ["--name", str(name)]

    # Let tournament.py handle run directory creation (no --json = auto run dir)
    # We don't pass --json so it uses the default results/runs/<id>/ path

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with _lock:
        _status = {
            "state": "running",
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": config,
            "command": " ".join(cmd),
            "output_lines": [],
            "run_id": run_id,
        }
        _process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(_REPO_ROOT),
        )

    reader = threading.Thread(target=_read_output, args=(_process,), daemon=True)
    reader.start()

    return {"ok": True, "config": config, "run_id": run_id}


def _list_runs() -> list[dict]:
    """List all tournament runs, newest first."""
    runs = []
    if not _RUNS_DIR.is_dir():
        return runs

    for run_dir in sorted(_RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        json_file = run_dir / "tournament_results.json"
        if not json_file.exists():
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            cfg = data.get("config", {})
            runs.append({
                "run_id": run_dir.name,
                "name": cfg.get("name", ""),
                "timestamp": data.get("timestamp", ""),
                "num_games": cfg.get("num_games"),
                "repetitions": cfg.get("repetitions"),
                "shock_scale": cfg.get("shock_scale", 0),
                "num_rounds": len(data.get("rounds", [])),
                "num_strategies": len(data.get("leaderboard", [])),
            })
        except (json.JSONDecodeError, OSError):
            runs.append({"run_id": run_dir.name, "timestamp": "", "error": True})
    return runs


def _get_run_json(run_id: str | None) -> Path | None:
    """Get the JSON file for a specific run or latest."""
    if run_id:
        p = _RUNS_DIR / run_id / "tournament_results.json"
        if p.exists():
            return p
    # Fallback to latest.json
    latest = _RESULTS_DIR / "latest.json"
    if latest.exists():
        return latest
    # Legacy fallback
    legacy = _RESULTS_DIR / "tournament_results.json"
    if legacy.exists():
        return legacy
    return None


# ── HTTP Handler ────────────────────────────────────────────

class DashboardHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(_DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # API: tournament status
        if path == "/api/status":
            return self._json_response(self._get_status())

        # API: tournament output log
        if path == "/api/log":
            with _lock:
                lines = list(_status.get("output_lines", []))
            return self._json_response({"lines": lines})

        # API: list all runs
        if path == "/api/runs":
            return self._json_response({"runs": _list_runs()})

        # Serve results JSON (with optional ?run=<id>)
        if path == "/data/tournament_results.json":
            run_id = qs.get("run", [None])[0]
            results_file = _get_run_json(run_id)
            if results_file:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(results_file.read_bytes())
            else:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "No results yet"}')
            return

        # Serve static files from dashboard dir
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/tournament":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                config = json.loads(body)
            except json.JSONDecodeError:
                config = {}
            result = _launch_tournament(config)
            return self._json_response(result)

        if path == "/api/stop":
            return self._json_response(self._stop_tournament())

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def _get_status(self) -> dict:
        with _lock:
            status = {
                "state": _status["state"],
                "started_at": _status.get("started_at"),
                "finished_at": _status.get("finished_at"),
                "exit_code": _status.get("exit_code"),
                "config": _status.get("config"),
                "output_line_count": len(_status.get("output_lines", [])),
                "run_id": _status.get("run_id"),
            }
        latest = _RESULTS_DIR / "latest.json"
        status["has_results"] = latest.exists() or (_RESULTS_DIR / "tournament_results.json").exists()
        return status

    def _stop_tournament(self) -> dict:
        global _process
        with _lock:
            if _process is not None and _process.poll() is None:
                _process.terminate()
                _status["state"] = "stopped"
                return {"ok": True, "message": "Tournament stopped"}
            return {"ok": False, "message": "No tournament running"}

    def _json_response(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if args and "404" not in str(args[0]) and "500" not in str(args[0]):
            return


def main():
    parser = argparse.ArgumentParser(description="Wordle Tournament Dashboard Server")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host (default: 0.0.0.0)")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{args.port}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
