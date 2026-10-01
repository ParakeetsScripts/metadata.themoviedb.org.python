#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " TMDB Kodi Scraper — development"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Project: $ROOT"
echo ""

python3 -m pip install mock coverage -q 2>/dev/null || true

echo "Running unit tests..."
PYTHONPATH=python python3 -m unittest discover -s test/unittests -p 'test_*.py' -v

echo ""
echo "All tests passed. This addon runs inside Kodi — there is no web dev server."
echo ""
KODI_ADDONS="$HOME/Library/Application Support/Kodi/addons"
KODI_TARGET="$KODI_ADDONS/metadata.themoviedb.org.python"
echo "Install in Kodi (symlink into addons folder):"
if mkdir -p "$KODI_ADDONS" 2>/dev/null; then
  ln -sfn "$ROOT" "$KODI_TARGET"
  echo "  Linked → $KODI_TARGET"
else
  echo "  mkdir -p \"$KODI_ADDONS\""
  echo "  ln -sfn \"$ROOT\" \"$KODI_TARGET\""
fi
echo ""
echo "FlutterFilms web app (separate project):"
echo "  cd /Users/rpm/vitamovies && npm run dev"
echo "  → http://localhost:3000"
echo ""
