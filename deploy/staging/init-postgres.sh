#!/bin/sh
set -eu

AION_MIGRATOR_PASSWORD="$(cat /run/secrets/migrator_password)" \
AION_RUNTIME_PASSWORD="$(cat /run/secrets/runtime_password)" \
psql --no-psqlrc --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 <<'SQL'
\getenv migrator_password AION_MIGRATOR_PASSWORD
\getenv runtime_password AION_RUNTIME_PASSWORD
CREATE ROLE aion_migrator LOGIN PASSWORD :'migrator_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE aion_runtime LOGIN PASSWORD :'runtime_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE aion OWNER aion_migrator;
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
\connect aion
REVOKE ALL ON DATABASE aion FROM PUBLIC;
GRANT CONNECT ON DATABASE aion TO aion_runtime;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO aion_runtime;
SQL
