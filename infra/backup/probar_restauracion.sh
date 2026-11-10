#!/bin/sh
# UNA prueba de restauracion en un servidor Postgres temporal propio (change 27b; D10; D14;
# docs/02 §16.2; docs/00 §9 criterio 12). Uso: probar_restauracion.sh [ARCHIVO]
#
# Sin red, sin credenciales de la base: levanta DENTRO del contenedor un servidor Postgres
# nuevo (otro servidor, otros datos, solo por socket local), crea los tres roles de la
# aplicacion sin ingreso, restaura el backup indicado (o el valido mas reciente de BACKUP_DIR)
# con restaurar.sh, lo comprueba con comprobar.sh y descarta todo. Deja en ESTADO_DIR la ultima
# corrida (`ultimo`: ok|fallo) y la fecha de la ultima buena (`ultima_buena`) para salud_prueba.sh.
#
# Variables: BACKUP_DIR (por defecto /backups, solo lectura), ESTADO_DIR (por defecto
# /estado-prueba) y AVISO_URL (opcional, D14).

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
ESTADO_DIR="${ESTADO_DIR:-/estado-prueba}"
. "$DIR_SCRIPTS/lib_restaurar.sh"

# Ningun dato de conexion del entorno se usa: la prueba trae su propio servidor.
unset PGPASSWORD PGPORT PGSERVICE PGPASSFILE PGHOST PGUSER PGDATABASE

base=""
descartado=0

# Descarta el servidor temporal y su carpeta (se llama siempre, bien o mal).
descartar() {
  [ "$descartado" -eq 0 ] || return 0
  descartado=1
  [ -n "$base" ] || return 0
  if [ -d "$base/datos" ]; then
    pg_ctl -D "$base/datos" -m immediate -w -s stop >/dev/null 2>&1 || true
  fi
  rm -rf "$base"
  if [ -e "$base" ]; then
    registrar "ERROR: no se pudo borrar la carpeta temporal de la prueba" >&2
  else
    registrar "Servidor temporal descartado"
  fi
}
trap 'descartar' EXIT

# Registra el error, deja la corrida como fallida, avisa y termina.
fallar() {
  registrar "ERROR: $*" >&2
  mkdir -p "$ESTADO_DIR" 2>/dev/null
  echo fallo > "$ESTADO_DIR/ultimo" 2>/dev/null
  descartar
  avisar fallo
  exit 1
}

[ "$(id -u)" != "0" ] || { registrar "ERROR: la prueba debe correr sin privilegios (usuario distinto de root): Postgres no arranca como superusuario del sistema" >&2; exit 1; }

# Elige el backup: el indicado o el valido mas reciente por la fecha de su nombre.
if [ -n "${1:-}" ]; then
  archivo=$(resolver_archivo "$1") || exit 1
else
  nombre=$(ls -1 "$BACKUP_DIR" 2>/dev/null | grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$' | LC_ALL=C sort | tail -n 1)
  [ -n "$nombre" ] || fallar "no hay ningun backup valido en $BACKUP_DIR"
  archivo="$BACKUP_DIR/$nombre"
fi
nombre=$(basename "$archivo")
registrar "Prueba de restauracion de $nombre en un servidor temporal"

base=$(mktemp -d) || fallar "no se pudo crear la carpeta temporal"
initdb -D "$base/datos" -U postgres -A trust -E UTF8 --no-sync >"$base/initdb.log" 2>&1 \
  || fallar "initdb fallo: $(tr '\n' ' ' < "$base/initdb.log" | cut -c1-200)"
pg_ctl -D "$base/datos" -w -s -l "$base/servidor.log" \
  -o "-c listen_addresses= -c unix_socket_directories=$base -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=20" start \
  || fallar "el servidor temporal no arranco: $(tr '\n' ' ' < "$base/servidor.log" | cut -c1-200)"

export PGHOST="$base" PGUSER=postgres
# Los tres roles de la aplicacion, sin ingreso ni contrasena; la base con el mismo dueno y
# permisos de esquema que deja init-app-roles.sh.
psql -X -q -v ON_ERROR_STOP=1 -d postgres <<'EOSQL' || fallar "no se pudieron preparar los roles y la base temporal"
CREATE ROLE app_migrations NOLOGIN;
CREATE ROLE app_runtime NOLOGIN;
CREATE ROLE app_backup NOLOGIN;
CREATE DATABASE distribuidora OWNER app_migrations;
EOSQL
export PGDATABASE=distribuidora
psql -X -q -v ON_ERROR_STOP=1 <<'EOSQL' || fallar "no se pudo preparar el esquema de la base temporal"
ALTER SCHEMA public OWNER TO app_migrations;
GRANT USAGE ON SCHEMA public TO app_runtime;
EOSQL

resultado=$(sh "$DIR_SCRIPTS/restaurar.sh" "$archivo" 2>&1) || {
  echo "$resultado" >&2
  fallar "la prueba de restauracion de $nombre fallo"
}
resumen=$(echo "$resultado" | sed -n 's/.*Restauracion verificada: \([0-9]*\) tablas, \([0-9]*\) filas.*/tablas=\1 filas=\2/p' | tail -n 1)
[ -n "$resumen" ] || fallar "no se pudo leer el resultado de la restauracion de $nombre"

descartar
mkdir -p "$ESTADO_DIR" 2>/dev/null
date +%s > "$ESTADO_DIR/ultima_buena" 2>/dev/null
echo ok > "$ESTADO_DIR/ultimo" 2>/dev/null
registrar "Prueba de restauracion verificada: archivo=$nombre $resumen"
avisar ok
