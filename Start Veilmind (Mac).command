#!/bin/bash
# Double-click in Finder. If macOS blocks it: right-click -> Open, or run:  python3 start.py
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 start.py "$@"
else
  echo "Python 3.10+ is not installed. Opening the download page..."
  open "https://www.python.org/downloads/"
fi
echo; read -n 1 -s -r -p "Press any key to close"
