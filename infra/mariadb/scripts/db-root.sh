#!/usr/bin/env bash
# MariaDB client as root inside the container. The password stays in the container env,
# never on the host command line.  e.g. scripts/db-root.sh -e "status"
source "$(dirname "$0")/_common.sh"; load_env
exec "${DOCKER[@]}" exec -i "$CONTAINER" sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot "$@"' sh "$@"
