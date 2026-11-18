#!/bin/bash
# FastReads Taso — Linux and macOS. No installation/build step.
set -e
cd "$(dirname "$0")"
for viewer_python in python3 python; do
  if command -v "$viewer_python" >/dev/null 2>&1 && "$viewer_python" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    exec "$viewer_python" launch.py
  fi
done
echo "FastReads Taso requires Python 3.10 or newer on PATH."
exit 1
