#!/usr/bin/env bash
# Idempotent: creates DIT NOW databases/users and (re)applies passwords + grants from .env.
# SQL is sent over stdin, so passwords never appear in process arguments.
source "$(dirname "$0")/_common.sh"; load_env
NET="${DB_USER_HOST:?set DB_USER_HOST in .env}"
scripts/db-root.sh <<SQL
CREATE DATABASE IF NOT EXISTS ditnow         CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ditnow_chatbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'ditnow_migrator'@'$NET';
ALTER  USER 'ditnow_migrator'@'$NET' IDENTIFIED BY '$DB_MIGRATOR_PASSWORD' WITH MAX_USER_CONNECTIONS 5;
GRANT ALL PRIVILEGES ON ditnow.*         TO 'ditnow_migrator'@'$NET';
GRANT ALL PRIVILEGES ON ditnow_chatbot.* TO 'ditnow_migrator'@'$NET';

CREATE USER IF NOT EXISTS 'ditnow_app'@'$NET';
ALTER  USER 'ditnow_app'@'$NET' IDENTIFIED BY '$DB_APP_PASSWORD' WITH MAX_USER_CONNECTIONS 50;
GRANT SELECT, INSERT, UPDATE, DELETE ON ditnow.*         TO 'ditnow_app'@'$NET';
GRANT SELECT                         ON ditnow_chatbot.* TO 'ditnow_app'@'$NET';

CREATE USER IF NOT EXISTS 'ditnow_chatbot'@'$NET';
ALTER  USER 'ditnow_chatbot'@'$NET' IDENTIFIED BY '$DB_CHATBOT_PASSWORD' WITH MAX_USER_CONNECTIONS 20;
GRANT SELECT, INSERT, UPDATE, DELETE ON ditnow_chatbot.* TO 'ditnow_chatbot'@'$NET';
GRANT SELECT                         ON ditnow.*         TO 'ditnow_chatbot'@'$NET';

CREATE USER IF NOT EXISTS 'ditnow_backup'@'localhost';
ALTER  USER 'ditnow_backup'@'localhost' IDENTIFIED BY '$DB_BACKUP_PASSWORD';
GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT ON *.* TO 'ditnow_backup'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "provisioned"
