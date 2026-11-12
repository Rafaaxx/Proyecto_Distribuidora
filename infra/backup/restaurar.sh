#!/bin/sh
# Restaura UN backup en una base VACIA (change 27b; D8; docs/02 §16.2; INV-05; ADR-020).
# Uso: restaurar.sh ARCHIVO   (nombre o ruta; se busca en BACKUP_DIR y en BACKUP_DIR/bajados)
#
# Conexion por las variables PG* con el rol DUENO DEL ESQUEMA (`app_migrations`), nunca el
# superusuario. Antes de tocar nada: verifica el archivo (pg_restore --list y las cuatro tablas
# de libro), se niega si la base tiene alguna tabla en `public` y se niega si hay otras
# conexiones a la base (el backend debe estar detenido). Restaura en UNA transaccion y se
# detiene en el primer error: si algo falla, la base queda vacia como estaba. Los duenos y los
# GRANT del archivo se conservan (app_runtime sigue sin UPDATE/DELETE en libros). Al terminar
# corre comprobar.sh (conteos por tabla, permisos y version de migraciones).

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
. "$DIR_SCRIPTS/lib_restaurar.sh"

[ -n "${1:-}" ] || fallar "uso: restaurar.sh ARCHIVO"
archivo=$(resolver_archivo "$1") || exit 1
verificar_archivo "$archivo"

tablas=$(consultar "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'") \
  || fallar "no se pudo consultar la base de destino"
[ "$tablas" = "0" ] || fallar "la base de destino no esta vacia (tiene $tablas tablas): no se restaura nada"

otras=$(consultar "SELECT count(*) FROM pg_stat_activity WHERE datid = (SELECT oid FROM pg_database WHERE datname = current_database()) AND pid <> pg_backend_pid() AND usename IS NOT NULL") \
  || fallar "no se pudo consultar las conexiones a la base"
[ "$otras" = "0" ] || fallar "hay $otras conexiones abiertas a la base: detenga el backend (docker compose stop backend) y vuelva a intentar"

registrar "Restaurando $(basename "$archivo") en la base $PGDATABASE"
pg_restore --single-transaction --exit-on-error --dbname "$PGDATABASE" "$archivo" \
  || fallar "la restauracion fallo; al ser una sola transaccion la base quedo vacia como estaba"

resultado=$(sh "$DIR_SCRIPTS/comprobar.sh" "$archivo" 2>&1) || {
  echo "$resultado" >&2
  fallar "la restauracion termino pero la comprobacion de los datos fallo"
}
registrar "Restauracion verificada: ${resultado#*Comprobacion correcta: }"
