#!/usr/bin/env bash
# Write per-role connection files to secrets/{fastapi,migrator,chatbot}.env (mode 600) for
# hand-off through an approved secret store. Usage: scripts/export-role-env.sh [db-host] [db-port]
# DATABASE_URL uses the async aiomysql driver (SQLAlchemy create_async_engine), matching chatbot/.
source "$(dirname "$0")/_common.sh"; load_env
host=${1:-${DB_BIND_ADDR:-127.0.0.1}}; port=${2:-${DB_HOST_PORT:-3307}}
umask 077; mkdir -p secrets
write() { # file user db password-variable
  local pw=${!4}
  require_password "$4"
  cat > "secrets/$1.env" <<ENV
# DIT NOW DB connection ($2) — SECRET. Approved secret store only; never Git/chat.
DB_HOST=$host
DB_PORT=$port
DB_NAME=$3
DB_USER=$2
DB_PASSWORD=$pw
DATABASE_URL=mysql+aiomysql://$2:$pw@$host:$port/$3?charset=utf8mb4
ENV
  echo "secrets/$1.env"
}
write fastapi  ditnow_app      ditnow         DB_APP_PASSWORD
write migrator ditnow_migrator ditnow         DB_MIGRATOR_PASSWORD
write chatbot  ditnow_chatbot  ditnow_chatbot DB_CHATBOT_PASSWORD
