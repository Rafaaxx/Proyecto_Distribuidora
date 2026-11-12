#!/bin/bash
# Provisiona los dos roles de aplicación que exige INV-05 (`ADR-020`,
# `design.md` D3 del change 03): `app_migrations` (dueño del esquema,
# usado solo por Alembic) y `app_runtime` (usado solo por el backend en
# runtime, con permisos otorgados tabla por tabla en cada migración).
#
# La imagen oficial de PostgreSQL corre todo lo que encuentre en
# `/docker-entrypoint-initdb.d/` la PRIMERA vez que se inicializa el volumen
# de datos (`postgres_data` en `docker-compose.yml`). Si el volumen ya
# existe de una corrida anterior con un solo rol, este script NO se vuelve
# a ejecutar solo: hay que recrear el volumen, o crear los roles a mano
# (ver README) contra la base ya levantada.
#
# Falla explícito (por `set -e` y por la ausencia de valor por omisión de
# las dos variables) si `APP_MIGRATIONS_DB_PASSWORD`/`APP_RUNTIME_DB_PASSWORD`
# no están definidas: ningún secreto de este proyecto tiene valor por
# defecto (`CLAUDE.md` §4).
set -euo pipefail

: "${APP_MIGRATIONS_DB_PASSWORD:?Definí APP_MIGRATIONS_DB_PASSWORD antes de levantar postgres}"
: "${APP_RUNTIME_DB_PASSWORD:?Definí APP_RUNTIME_DB_PASSWORD antes de levantar postgres}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_migrations') THEN
            CREATE ROLE app_migrations LOGIN PASSWORD '${APP_MIGRATIONS_DB_PASSWORD}';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_runtime') THEN
            CREATE ROLE app_runtime LOGIN PASSWORD '${APP_RUNTIME_DB_PASSWORD}';
        END IF;
    END
    \$\$;

    -- app_migrations es dueño del esquema (D3): puede crear, alterar y
    -- borrar objetos. app_runtime solo recibe USAGE acá; el
    -- SELECT/INSERT/UPDATE/DELETE por tabla lo otorga cada migración que
    -- crea o modifica una tabla (ADR-020).
    ALTER SCHEMA public OWNER TO app_migrations;
    GRANT USAGE ON SCHEMA public TO app_runtime;
EOSQL
