#!/usr/bin/env bash
# Create .env from .env.example with random 32-char passwords. Refuses to overwrite.
source "$(dirname "$0")/_common.sh"
[ -f .env ] && { echo "ERROR: .env already exists; not overwriting." >&2; exit 1; }
umask 077
gen() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32; }
tmp=$(mktemp .env.XXXXXX); trap 'rm -f "$tmp"' EXIT
while IFS= read -r line; do
  case "$line" in
    *_PASSWORD=CHANGE_ME)
      pw=$(gen) || pw=""
      [ ${#pw} -eq 32 ] || { echo "ERROR: password generation failed (openssl?)" >&2; exit 1; }
      echo "${line%%=*}=$pw" ;;
    *) echo "$line" ;;
  esac
done < .env.example > "$tmp"
mv "$tmp" .env
echo "created .env (mode 600). Review non-secret settings before 'docker compose up -d'."
