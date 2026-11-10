#!/bin/sh
# Funciones comunes de restaurar.sh, comprobar.sh y probar_restauracion.sh (change 27b; D8, D9,
# D10). Se carga con `.`; no hace nada por si solo.

LIBROS="cuenta_movimiento stock_movimiento costo_producto_mov auditoria"

registrar() { echo "$(date '+%Y-%m-%d %H:%M:%S %z') $*"; }
fallar() { registrar "ERROR: $*" >&2; exit 1; }

# SQL de una sola consulta con la conexion de las variables PG*; imprime solo el resultado.
consultar() { psql -X -At -v ON_ERROR_STOP=1 -c "$1"; }

# Ruta completa del backup pedido. Acepta una ruta (con /) o un nombre: se busca en BACKUP_DIR y,
# si no esta, en la subcarpeta `bajados` (donde `copia-externa bajar` deja lo que descarga).
resolver_archivo() {
  case "$1" in
    */*) _ruta="$1" ;;
    *)
      _ruta="$BACKUP_DIR/$1"
      [ -f "$_ruta" ] || _ruta="$BACKUP_DIR/bajados/$1"
      ;;
  esac
  [ -f "$_ruta" ] || fallar "el archivo '$1' no existe (se busco en $BACKUP_DIR y en $BACKUP_DIR/bajados)"
  echo "$_ruta"
}

# Verifica que el archivo se pueda leer y traiga las cuatro tablas de libro (como respaldar.sh).
verificar_archivo() {
  _lista=$(pg_restore --list "$1" 2>/dev/null) || fallar "'$1' no es un backup valido: pg_restore no lo puede leer"
  for _libro in $LIBROS; do
    echo "$_lista" | grep -Eq " TABLE public $_libro " \
      || fallar "'$1' no es un backup valido de la distribuidora: le falta la tabla de libro $_libro"
  done
}

# Aviso externo opcional (D14): sin AVISO_URL no hace nada; con ella, llama a la direccion (o a
# `<direccion>/fail` con el argumento `fallo`). Nunca envia datos del negocio y un fallo del aviso
# no cambia el resultado de la prueba. La imagen no trae wget ni curl: usa HTTP::Tiny de perl.
avisar() {
  [ -n "${AVISO_URL:-}" ] || return 0
  _destino="$AVISO_URL"
  [ "$1" = "fallo" ] && _destino="${AVISO_URL%/}/fail"
  perl -MHTTP::Tiny -e 'exit(HTTP::Tiny->new(timeout => 10)->get($ARGV[0])->{success} ? 0 : 1)' "$_destino" 2>/dev/null \
    || registrar "AVISO: no se pudo llamar a la direccion de aviso" >&2
  return 0
}
