#!/usr/bin/env bash
# Restore a backup into ditnow_restore_test / ditnow_restore_test_chatbot (live DBs are never touched),
# print table row counts, then drop the test DBs unless --keep is given.
# Usage: scripts/restore-test.sh [backup.sql.gz] [--keep]   (default: newest backup)
source "$(dirname "$0")/_common.sh"; load_env
file=""; keep=0
for a in "$@"; do [ "$a" = --keep ] && keep=1 || file=$a; done
file=${file:-$(ls -t backups/ditnow_*.sql.gz 2>/dev/null | head -1)}
[ -n "$file" ] && [ -f "$file" ] || { echo "ERROR: no backup file found" >&2; exit 1; }
echo "restoring $file -> ditnow_restore_test*"
zcat "$file" | sed -E 's/`ditnow(_chatbot)?`/`ditnow_restore_test\1`/g' | scripts/db-root.sh
scripts/db-root.sh -e "SELECT schema_name AS restored_db,
                         (SELECT COUNT(*) FROM information_schema.tables t WHERE t.table_schema = s.schema_name) AS tables
                       FROM information_schema.schemata s WHERE schema_name LIKE 'ditnow_restore_test%';
                       SELECT table_schema, table_name, table_rows FROM information_schema.tables
                       WHERE table_schema LIKE 'ditnow_restore_test%' ORDER BY 1,2;"
if [ $keep -eq 0 ]; then
  scripts/db-root.sh -e "DROP DATABASE ditnow_restore_test; DROP DATABASE ditnow_restore_test_chatbot;"
  echo "restore test OK (test DBs dropped)"
fi
