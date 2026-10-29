#!/usr/bin/env bash
# Idempotent: creates DIT NOW databases/users and resets every service account to exactly the
# grants below (REVOKE then GRANT), using passwords from .env. Accounts of the same name on an
# old DB_USER_HOST (e.g. after a subnet change) are dropped.
# SQL is sent over stdin, so passwords never appear in process arguments.
source "$(dirname "$0")/_common.sh"; load_env
NET="${DB_USER_HOST:?set DB_USER_HOST in .env}"
for v in DB_MIGRATOR_PASSWORD DB_APP_PASSWORD DB_CHATBOT_PASSWORD DB_BACKUP_PASSWORD; do require_password "$v"; done

stale=$(scripts/db-root.sh -N -e "SELECT CONCAT('''', user, '''@''', host, '''') FROM mysql.user
  WHERE (user IN ('ditnow_migrator','ditnow_app','ditnow_chatbot') AND host <> '$NET')
     OR (user = 'ditnow_backup' AND host <> 'localhost');")
for acct in $stale; do echo "dropping stale account $acct"; done

scripts/db-root.sh <<SQL
CREATE DATABASE IF NOT EXISTS ditnow         CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ditnow_chatbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
$(for acct in $stale; do echo "DROP USER $acct;"; done)

CREATE USER IF NOT EXISTS 'ditnow_migrator'@'$NET';
ALTER  USER 'ditnow_migrator'@'$NET' IDENTIFIED BY '$DB_MIGRATOR_PASSWORD' WITH MAX_USER_CONNECTIONS 5;
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'ditnow_migrator'@'$NET';
GRANT ALL PRIVILEGES ON ditnow.*         TO 'ditnow_migrator'@'$NET';
GRANT ALL PRIVILEGES ON ditnow_chatbot.* TO 'ditnow_migrator'@'$NET';

CREATE USER IF NOT EXISTS 'ditnow_app'@'$NET';
ALTER  USER 'ditnow_app'@'$NET' IDENTIFIED BY '$DB_APP_PASSWORD' WITH MAX_USER_CONNECTIONS 50;
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'ditnow_app'@'$NET';
GRANT SELECT, INSERT, UPDATE, DELETE ON ditnow.*         TO 'ditnow_app'@'$NET';
GRANT SELECT                         ON ditnow_chatbot.* TO 'ditnow_app'@'$NET';

CREATE USER IF NOT EXISTS 'ditnow_chatbot'@'$NET';
ALTER  USER 'ditnow_chatbot'@'$NET' IDENTIFIED BY '$DB_CHATBOT_PASSWORD' WITH MAX_USER_CONNECTIONS 20;
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'ditnow_chatbot'@'$NET';
GRANT SELECT, INSERT, UPDATE, DELETE ON ditnow_chatbot.* TO 'ditnow_chatbot'@'$NET';
GRANT SELECT                         ON ditnow.*         TO 'ditnow_chatbot'@'$NET';

-- backup: dump-only rights on the two DIT NOW databases (no access to the mysql schema)
CREATE USER IF NOT EXISTS 'ditnow_backup'@'localhost';
ALTER  USER 'ditnow_backup'@'localhost' IDENTIFIED BY '$DB_BACKUP_PASSWORD';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'ditnow_backup'@'localhost';
GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT, SHOW CREATE ROUTINE ON ditnow.*         TO 'ditnow_backup'@'localhost';
GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT, SHOW CREATE ROUTINE ON ditnow_chatbot.* TO 'ditnow_backup'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "provisioned"
