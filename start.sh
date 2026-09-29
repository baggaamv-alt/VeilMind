#!/usr/bin/env bash
# Linux / macOS terminal:  ./start.sh   (or:  python3 start.py)
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; fi
exec "$PY" start.py "$@"
