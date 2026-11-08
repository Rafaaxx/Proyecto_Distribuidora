#!/bin/bash
# Crea el rol de SOLO LECTURA con el que trabaja el servicio de backups (change 27a, D11;
# amplia ADR-020 y respeta INV-05).
#
# `app_backup` puede iniciar sesion y es miembro de `pg_read_all_data` (rol predefinido de
# PostgreSQL 14+): lee todas las tablas y secuencias, tambien las que creen migraciones
# futuras. No puede insertar, modificar, borrar ni crear nada.
#
# Se monta SOLO en el compose de produccion, junto a `10-init-app-roles.sh`. Corre la primera
# vez que se inicializa el volumen de datos; si el volumen ya existia, el runbook trae el SQL
# para crear el rol a mano.
#
# Sin valor por defecto: si falta la contrasena, falla y avisa (CLAUDE.md §4).
set -euo pipefail

: "${APP_BACKUP_DB_PASSWORD:?Defina APP_BACKUP_DB_PASSWORD antes de levantar postgres}"

# La contrasena viaja como variable de psql (:'clave'), no pegada en el SQL: queda bien
# escapada aunque tenga caracteres especiales.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v clave="$APP_BACKUP_DB_PASSWORD" <<'EOSQL'
SELECT format('CREATE ROLE app_backup LOGIN PASSWORD %L', :'clave')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_backup')
\gexec

GRANT pg_read_all_data TO app_backup;
EOSQL
