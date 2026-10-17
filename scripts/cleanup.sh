#!/usr/bin/env bash
# Remove build junk and stale generated files, and optionally reclaim Docker space.
#
# Usage:
#   scripts/cleanup.sh                 # repo caches, temp media, old exports
#   scripts/cleanup.sh --docker        # also prune dangling images/build cache
#   scripts/cleanup.sh --volumes       # also remove unused Docker volumes
#   RETENTION_DAYS=30 scripts/cleanup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DO_DOCKER=0
DO_VOLUMES=0

for arg in "$@"; do
    case "$arg" in
        --docker) DO_DOCKER=1 ;;
        --volumes) DO_DOCKER=1; DO_VOLUMES=1 ;;
        -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

echo "==> Removing Python caches"
find "$ROOT" -type d -name '__pycache__' -not -path '*/.git/*' -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -type d \( -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
    -not -path '*/.git/*' -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

echo "==> Removing .NET build output"
find "$ROOT/client" -type d \( -name bin -o -name obj \) -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> Removing stray audio and log files"
find "$ROOT/server" "$ROOT/client" -type f \( -name '*.wav' -o -name '*.mp3' -o -name '*.pcm' -o -name '*.log' \) \
    -delete 2>/dev/null || true

echo "==> Pruning generated exports older than ${RETENTION_DAYS} days"
find "$ROOT/server/data/exports" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" \
    -exec rm -rf {} + 2>/dev/null || true

if [ "$DO_DOCKER" = "1" ]; then
    if command -v docker >/dev/null 2>&1; then
        echo "==> Pruning Docker build cache and dangling images"
        docker builder prune -f
        docker image prune -f
        if [ "$DO_VOLUMES" = "1" ]; then
            echo "==> Pruning unused Docker volumes"
            docker volume prune -f
        fi
        docker system df
    else
        echo "docker not found; skipping Docker cleanup" >&2
    fi
fi

echo "==> Done"
