#!/usr/bin/env bash
# Shared helpers, sourced by the other scripts. Not meant to be run directly.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

load_env() {
  [ -f .env ] || { echo "ERROR: .env not found. Run scripts/gen-env.sh first." >&2; exit 1; }
  set -a; . ./.env; set +a
  CONTAINER="${DB_CONTAINER_NAME:-ditnow-db}"
}

# Use docker directly when the current user can, otherwise fall back to sudo.
if docker info >/dev/null 2>&1; then DOCKER=(docker); else DOCKER=(sudo docker); fi

# Read one value from .env without exporting anything else.
env_get() { grep "^$1=" .env | cut -d= -f2- | sed 's/[[:space:]]*#.*//; s/[[:space:]]*$//'; }
