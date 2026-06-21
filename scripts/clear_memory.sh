#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT_DIR}/memory/data"
ARCHIVE_DIR="${ROOT_DIR}/memory/archive"
ASSUME_YES=false

usage() {
  cat <<'EOF'
Usage: ./scripts/clear_memory.sh [--yes]

Clear all Workmate runtime memory, including conversations, tasks, profiles,
screen observations, screenshots, ChromaDB indices, and archived backups.

Options:
  -y, --yes   Skip the interactive confirmation.
  -h, --help  Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)
      ASSUME_YES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if command -v pgrep >/dev/null 2>&1 && pgrep -f 'python.*-m[[:space:]]+src\.web' >/dev/null 2>&1; then
  printf '%s\n' 'Workmate Agent is still running.' >&2
  printf '%s\n' 'Stop it with Ctrl+C in its terminal, then run this script again.' >&2
  exit 1
fi

if [[ "$ASSUME_YES" != true ]]; then
  printf '%s\n' 'This permanently deletes all local Workmate memory and backups.'
  printf '%s' 'Type CLEAR to continue: '
  read -r confirmation
  if [[ "$confirmation" != "CLEAR" ]]; then
    printf '%s\n' 'Cancelled.'
    exit 0
  fi
fi

mkdir -p "$DATA_DIR/daily_summaries" "$ARCHIVE_DIR"

find "$DATA_DIR" -mindepth 1 -maxdepth 1 \
  ! -name '.gitkeep' \
  ! -name 'daily_summaries' \
  -exec rm -rf -- {} +

find "$DATA_DIR/daily_summaries" -mindepth 1 \
  ! -name '.gitkeep' \
  -exec rm -rf -- {} +

find "$ARCHIVE_DIR" -mindepth 1 -exec rm -rf -- {} +

touch "$DATA_DIR/.gitkeep" "$DATA_DIR/daily_summaries/.gitkeep"

printf '%s\n' 'Workmate memory cleared.'
printf '%s\n' 'Run ./run.sh to start again from an empty state.'
