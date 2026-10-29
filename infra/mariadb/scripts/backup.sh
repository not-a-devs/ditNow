#!/usr/bin/env bash
# Logical backup of ditnow + ditnow_chatbot -> backups/ditnow_<ts>.sql.gz (mode 600).
# Deletes backups older than BACKUP_RETENTION_DAYS (default 14).
source "$(dirname "$0")/_common.sh"; load_env
umask 077
mkdir -p backups
out="backups/ditnow_$(date +%Y%m%d_%H%M%S).sql.gz"
env_get DB_BACKUP_PASSWORD | \
  "${DOCKER[@]}" exec -i "$CONTAINER" sh -c 'read -r MYSQL_PWD; export MYSQL_PWD; exec mariadb-dump -uditnow_backup \
    --single-transaction --routines --triggers --events --hex-blob --databases ditnow ditnow_chatbot' \
  | gzip -9 > "$out.part"
gzip -t "$out.part" && mv "$out.part" "$out"
find backups -name 'ditnow_*.sql.gz' -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
echo "$out $(du -h "$out" | cut -f1)"
