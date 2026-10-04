#!/usr/bin/env bash
# Runs once when the PostgreSQL volume is created. Creates the least-privilege roles and the
# databases. Passwords come from the environment (local) or the secret store (deployments).
set -euo pipefail
: "${JDHP_DB_APP_PASSWORD:?}"; : "${JDHP_DB_WORKER_PASSWORD:?}"; : "${JDHP_DB_MIGRATE_PASSWORD:?}"; : "${KC_DB_PASSWORD:?}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
  CREATE ROLE jdhp_migrate LOGIN PASSWORD '${JDHP_DB_MIGRATE_PASSWORD}' NOBYPASSRLS;
  CREATE ROLE jdhp_app LOGIN PASSWORD '${JDHP_DB_APP_PASSWORD}' NOBYPASSRLS;
  CREATE ROLE jdhp_worker LOGIN PASSWORD '${JDHP_DB_WORKER_PASSWORD}' NOBYPASSRLS;
  CREATE ROLE keycloak LOGIN PASSWORD '${KC_DB_PASSWORD}';
  CREATE DATABASE jdhp OWNER jdhp_migrate;
  CREATE DATABASE keycloak OWNER keycloak;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname jdhp <<SQL
  CREATE EXTENSION IF NOT EXISTS vector;
  GRANT USAGE ON SCHEMA public TO jdhp_app, jdhp_worker;
  ALTER DEFAULT PRIVILEGES FOR ROLE jdhp_migrate IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO jdhp_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE jdhp_migrate IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO jdhp_app, jdhp_worker;
SQL
echo "roles and databases created"
