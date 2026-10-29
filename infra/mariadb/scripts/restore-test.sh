#!/usr/bin/env bash
# Restore a backup into ditnow_restore_test / ditnow_restore_test_chatbot (live DBs are never touched),
# compare every restored table with the live table (exact COUNT(*) + CHECKSUM TABLE), then drop the
# test DBs unless --keep is given. A DIFF can also mean live data changed after the backup was taken.
# Usage: scripts/restore-test.sh [backup.sql.gz] [--keep]   (default: newest backup)
source "$(dirname "$0")/_common.sh"; load_env
file=""; keep=0
for a in "$@"; do [ "$a" = --keep ] && keep=1 || file=$a; done
file=${file:-$(ls -t backups/ditnow_*.sql.gz 2>/dev/null | head -1 || true)}
[ -n "$file" ] && [ -f "$file" ] || { echo "ERROR: no backup file found" >&2; exit 1; }
echo "restoring $file -> ditnow_restore_test*"
zcat "$file" | sed -E 's/`ditnow(_chatbot)?`/`ditnow_restore_test\1`/g' | scripts/db-root.sh

tables=$(scripts/db-root.sh -N -e "SELECT CONCAT(table_schema, '.', table_name) FROM information_schema.tables
  WHERE table_schema IN ('ditnow_restore_test','ditnow_restore_test_chatbot') AND table_type = 'BASE TABLE'
  ORDER BY 1;")
status=0
printf '%-60s %10s %10s  %s\n' TABLE RESTORED LIVE RESULT
for t in $tables; do
  rs=${t%%.*}; tn=${t#*.}; ls_=${rs/ditnow_restore_test/ditnow}
  r=$(scripts/db-root.sh -N -e "SELECT COUNT(*) FROM \`$rs\`.\`$tn\`; CHECKSUM TABLE \`$rs\`.\`$tn\`;" | awk 'NR==1{c=$1} NR==2{print c, $2}')
  l=$(scripts/db-root.sh -N -e "SELECT COUNT(*) FROM \`$ls_\`.\`$tn\`; CHECKSUM TABLE \`$ls_\`.\`$tn\`;" 2>/dev/null | awk 'NR==1{c=$1} NR==2{print c, $2}' || true)
  if [ "$r" = "$l" ]; then res=MATCH; else res=DIFF; status=1; fi
  printf '%-60s %10s %10s  %s\n' "$ls_.$tn" "${r%% *}" "${l%% *}" "$res"
done
[ -n "$tables" ] || echo "(backup contains no tables)"

if [ $keep -eq 0 ]; then
  scripts/db-root.sh -e "DROP DATABASE ditnow_restore_test; DROP DATABASE ditnow_restore_test_chatbot;"
  echo "test DBs dropped"
fi
[ $status -eq 0 ] && echo "restore test OK" || echo "restore test: DIFF found (check whether live data changed after the backup)" >&2
exit $status
