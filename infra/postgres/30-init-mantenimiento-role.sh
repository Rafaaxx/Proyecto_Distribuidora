#!/bin/bash
# Crea el rol de las tareas periodicas (change 28, D3; amplia ADR-018 y ADR-020, respeta INV-05).
#
# `app_mantenimiento` puede iniciar sesion y NO tiene ningun permiso al crearse: los `GRANT`
# (leer los saldos y libros que compara la verificacion, insertar sus resultados y borrar
# intentos de inicio de sesion viejos) los otorga la migracion, como todo `GRANT` (ADR-020). No
# es superusuario, no crea roles ni bases y no es dueño de nada.
#
# Se monta en el compose de produccion y en el de desarrollo, junto a `10-init-app-roles.sh`.
# Corre solo la primera vez que se inicializa el volumen de datos. Si el volumen ya existia
# (un entorno en uso), hay que crear el rol a mano ANTES de migrar: el runbook trae los pasos
# (`docs/runbook/puesta-en-marcha.md`). La migracion falla, nombrando ese paso, si el rol no
# existe.
#
# Repetible: si el rol ya existe, no lo toca (ni cambia su contrasena).
# Sin valor por defecto: si falta la contrasena, falla y avisa (CLAUDE.md §4).
set -euo pipefail

: "${APP_MANTENIMIENTO_DB_PASSWORD:?Defina APP_MANTENIMIENTO_DB_PASSWORD antes de levantar postgres}"

# La contrasena viaja como variable de psql (:'clave'), no pegada en el SQL: queda bien
# escapada aunque tenga caracteres especiales.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v clave="$APP_MANTENIMIENTO_DB_PASSWORD" <<'EOSQL'
SELECT format('CREATE ROLE app_mantenimiento LOGIN PASSWORD %L', :'clave')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_mantenimiento')
\gexec
EOSQL
