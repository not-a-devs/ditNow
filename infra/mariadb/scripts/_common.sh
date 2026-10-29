#!/usr/bin/env bash
# Shared helpers, sourced by the other scripts. Not meant to be run directly.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Single way to read settings: source .env (shell quoting rules apply) and use the variables.
load_env() {
  [ -f .env ] || { echo "ERROR: .env not found. Run scripts/gen-env.sh first." >&2; exit 1; }
  set -a; . ./.env; set +a
  CONTAINER="${DB_CONTAINER_NAME:-ditnow-db}"
}

# Fail unless the named variable holds a usable password. Passwords are embedded in SQL
# string literals, so quotes and backslashes are rejected rather than escaped.
require_password() {
  local name=$1 value=${!1:-}
  case "$value" in
    ""|CHANGE_ME) echo "ERROR: $name is empty or CHANGE_ME in .env" >&2; exit 1 ;;
    *\'*|*\\*)    echo "ERROR: $name must not contain ' or \\" >&2; exit 1 ;;
  esac
  [ ${#value} -ge 16 ] || { echo "ERROR: $name must be at least 16 characters" >&2; exit 1; }
}

# Use docker directly when the current user can, otherwise fall back to sudo.
if docker info >/dev/null 2>&1; then DOCKER=(docker); else DOCKER=(sudo docker); fi
