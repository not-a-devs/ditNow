#!/usr/bin/env bash
# Connect as a service account over TCP, the same path an application uses.
# Usage: scripts/db-client.sh <app|migrator|chatbot> [mariadb args...]
#   DB_CLIENT_HOST=<addr> DB_CLIENT_PORT=<port> to test a remote path (e.g. Tailscale address).
source "$(dirname "$0")/_common.sh"; load_env
usage() { echo "usage: scripts/db-client.sh <app|migrator|chatbot> [mariadb args...]" >&2; exit 2; }
case "${1:-}" in
  app)      var=DB_APP_PASSWORD ;;
  migrator) var=DB_MIGRATOR_PASSWORD ;;
  chatbot)  var=DB_CHATBOT_PASSWORD ;;
  *)        usage ;;
esac
role=$1; shift
require_password "$var"
host=${DB_CLIENT_HOST:-${DB_BIND_ADDR:-127.0.0.1}}
port=${DB_CLIENT_PORT:-${DB_HOST_PORT:-3307}}
mkdir -p secrets && chmod 700 secrets
tmp=$(mktemp -p secrets); trap 'rm -f "$tmp"' EXIT
echo "MYSQL_PWD=${!var}" > "$tmp"
"${DOCKER[@]}" run --rm -i --network host --env-file "$tmp" "${DB_IMAGE:-mariadb:11.4}" \
  mariadb -h"$host" -P"$port" -u"ditnow_$role" "$@"
