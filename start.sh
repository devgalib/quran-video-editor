#!/usr/bin/env bash
# Opens the Quran Video Editor. The first run creates .venv and installs Pillow + PySide6.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python -m qve gui "$@"
