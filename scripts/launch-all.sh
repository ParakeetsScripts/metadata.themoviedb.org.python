#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILMS="/Users/rpm/vitamovies"

echo ""
echo "Launching both projects..."
echo ""

# 1. Kodi scraper — verify tests
cd "$ROOT"
bash scripts/dev.sh

# 2. FlutterFilms — start dev server if not already running
if curl -fsS "http://localhost:3000" >/dev/null 2>&1; then
  echo "FlutterFilms already running at http://localhost:3000"
else
  echo "Starting FlutterFilms dev server..."
  cd "$FILMS"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  (lsof -ti:3000 | xargs kill -9 2>/dev/null || true)
  npm run dev &
  sleep 3
  if curl -fsS "http://localhost:3000" >/dev/null 2>&1; then
    echo "FlutterFilms ready at http://localhost:3000"
  else
    echo "FlutterFilms is starting — open http://localhost:3000 in a few seconds."
  fi
fi

echo ""
echo "Done."
echo "  Kodi scraper:  $ROOT (tests OK — use in Kodi)"
echo "  FlutterFilms:  http://localhost:3000"
echo ""
