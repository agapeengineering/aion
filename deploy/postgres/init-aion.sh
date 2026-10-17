#!/bin/sh
set -eu
# Bootstrap a non-superuser application/database owner. Do not echo credentials.
AION_APP_PASSWORD="$(cat /run/secrets/app_database_password)" \
psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_password AION_APP_PASSWORD
CREATE ROLE aion_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE aion OWNER aion_app;
SQL
