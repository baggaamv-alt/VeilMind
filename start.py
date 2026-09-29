#!/usr/bin/env python3
"""Veilmind one-step launcher (Windows, macOS, Linux). Uses only the Python standard library.

    python start.py              # set up (first run only) and start, then open the browser
    python start.py --port 9000  # preferred port (the next free one is used if it's taken)
    python start.py --no-browser
    python start.py --reset      # delete local app data; synthetic data is re-seeded on start

First run needs internet once, to install packages. After that it works offline.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

MIN_PY = (3, 10)
ROOT = Path(__file__).resolve().parent
# one environment per OS + Python version, so a folder copied between laptops never reuses a broken venv
VENV: Path = ROOT / f".venv-{sys.platform}-py{sys.version_info[0]}{sys.version_info[1]}"
IS_WIN = os.name == "nt"


def say(msg: str) -> None:
    print(f"[veilmind] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\n[veilmind] ERROR: {msg}\n", flush=True)
    if IS_WIN and sys.stdin and sys.stdin.isatty():
        input("Press Enter to close...")
    sys.exit(1)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def works(py: Path) -> bool:
    try:
        return subprocess.run([str(py), "-c", "import sys; print(sys.version)"], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def ensure_venv() -> Path | None:
    """Returns the environment's python, or None if this Python can't make a venv (fallback: user install)."""
    py = venv_python()
    if py.exists() and works(py):
        return py
    if VENV.exists():
        say("Existing environment is broken or from another computer; recreating it...")
        shutil.rmtree(VENV, ignore_errors=True)
    say(f"Creating a private Python environment in {VENV.name} (first run only)...")
    r = subprocess.run([sys.executable, "-m", "venv", str(VENV)], capture_output=True, text=True)
    if r.returncode == 0 and works(py):
        return py
    shutil.rmtree(VENV, ignore_errors=True)
    say("This Python can't create a virtual environment; installing packages for your user account instead.")
    return None


def file_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def ensure_packages(py: Path | None) -> Path:
    core, live = ROOT / "requirements.txt", ROOT / "requirements-live.txt"
    user_mode = py is None
    marker = (ROOT / f".installed-user-{sys.platform}-py{sys.version_info[0]}{sys.version_info[1]}") if user_mode else (VENV / ".installed")
    run_py = Path(sys.executable) if user_mode else py
    want = file_hash(core, live)
    if marker.exists() and marker.read_text().strip() == want:
        return run_py
    say("Installing packages (first run only, needs internet)...")
    pip = [str(run_py), "-m", "pip", "--disable-pip-version-check", "install"]
    extra: list[str] = ["--user"] if user_mode else []
    if user_mode and subprocess.run([str(run_py), "-m", "pip", "--version"], capture_output=True).returncode != 0:
        subprocess.run([str(run_py), "-m", "ensurepip", "--user"], capture_output=True)
    else:
        subprocess.run(pip + extra + ["--upgrade", "pip"], capture_output=True)

    def install(req: Path) -> bool:
        r = subprocess.run(pip + extra + ["-r", str(req)], capture_output=user_mode, text=True)
        if r.returncode != 0 and user_mode and "externally-managed" in ((r.stderr or "") + (r.stdout or "")):
            # distro-managed Python (PEP 668): install into the user site only
            r = subprocess.run(pip + extra + ["--break-system-packages", "-r", str(req)])
        elif r.returncode != 0 and user_mode:
            print((r.stdout or "")[-2000:], (r.stderr or "")[-2000:])
        return r.returncode == 0

    if not install(core):
        fail("Package installation failed. Check your internet connection (or proxy) and run this again.")
    # Hindsight SDK is only needed with API keys; never block startup if it can't be installed here
    if live.exists() and not install(live):
        say("WARNING: hindsight-client could not be installed; the app still runs, but Hindsight keys won't be used.")
    marker.write_text(want)
    return run_py


def ensure_env_file() -> None:
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists() and example.exists():
        shutil.copy(example, env)
        say("Created .env from .env.example (add API keys there to use Hindsight + Groq).")


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    fail("No free port found between %d and %d." % (preferred, preferred + 49))
    return preferred


def wait_until_up(url: str, proc: subprocess.Popen, seconds: int = 90) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Start Veilmind")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--reset", action="store_true", help="delete local app data before starting")
    args = ap.parse_args()

    if sys.version_info < MIN_PY:
        fail(f"Python {MIN_PY[0]}.{MIN_PY[1]} or newer is required (this is {platform.python_version()}). "
             "Install it from https://www.python.org/downloads/")
    os.chdir(ROOT)
    say(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    py = ensure_packages(ensure_venv())
    ensure_env_file()
    if args.reset:
        for f in ROOT.glob("veilmind.sqlite3*"):
            f.unlink(missing_ok=True)
        say("Local data reset.")

    port = free_port(args.port)
    if port != args.port:
        say(f"Port {args.port} is busy; using {port}.")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    cmd = [str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    say("Starting server...")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    url = f"http://127.0.0.1:{port}"
    if not wait_until_up(f"{url}/api/health", proc):
        proc.terminate()
        fail("The server did not start. See the messages above.")
    print(f"\n  Veilmind is running:\n    Landing page : {url}/\n    Dashboard    : {url}/app\n    Guided demo  : {url}/app?demo=1\n\n  Press Ctrl+C to stop.\n", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(f"{url}/")
        except Exception:
            pass
    try:
        proc.wait()
    except KeyboardInterrupt:
        say("Stopping...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
