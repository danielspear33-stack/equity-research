#!/bin/bash
# Mac launcher: double-click to start the app.
cd "$(dirname "$0")" || exit 1
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
  echo "Python isn't installed. Get it from python.org, then try again."
  read -r -p "Press Enter to close."
  exit 1
fi
"$PYTHON" launch.py || read -r -p "Press Enter to close."
