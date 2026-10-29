#!/usr/bin/env bash
# Create .env from .env.example with random 32-char passwords. Refuses to overwrite.
source "$(dirname "$0")/_common.sh"
[ -f .env ] && { echo "ERROR: .env already exists; not overwriting." >&2; exit 1; }
umask 077
gen() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32; }
while IFS= read -r line; do
  case "$line" in
    *_PASSWORD=CHANGE_ME) echo "${line%%=*}=$(gen)" ;;
    *) echo "$line" ;;
  esac
done < .env.example > .env
echo "created .env (mode 600). Review non-secret settings before 'docker compose up -d'."
