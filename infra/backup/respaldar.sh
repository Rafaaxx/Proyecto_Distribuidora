#!/bin/sh
# Hace UN backup completo de la base, lo verifica y aplica la retencion (change 27a; D10, D12,
# D13; docs/02 §16.2, docs/00 §9 criterio 12).
#
# Variables (las de conexion son las estandar de PostgreSQL):
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE   conexion con el rol de solo lectura
#   BACKUP_DIR         carpeta de destino              (por defecto /backups)
#   BACKUP_RETENCION   cuantos backups validos quedan  (por defecto 7)
#
# Pasos: pg_dump -Fc a un archivo .tmp -> verificacion con pg_restore --list (deben estar las
# cuatro tablas de libro) -> renombre a .dump -> retencion. Si algo falla no queda ningun .dump
# nuevo: un archivo ilegible pasa a .fallido (se conserva para revisarlo) y un corte a mitad
# del dump borra el .tmp. Los registros no incluyen datos del negocio.

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENCION="${BACKUP_RETENCION:-7}"
LIBROS="cuenta_movimiento stock_movimiento costo_producto_mov auditoria"

registrar() { echo "$(date '+%Y-%m-%d %H:%M:%S %z') $*"; }
fallar() { registrar "ERROR: $*" >&2; exit 1; }

case "$BACKUP_RETENCION" in
  ''|*[!0-9]*|0) fallar "BACKUP_RETENCION debe ser un numero entero mayor que 0 (valor recibido: '$BACKUP_RETENCION')" ;;
esac

# Solo el usuario que corre el servicio lee lo que se cree. En una carpeta de Windows montada
# (Docker Desktop) los permisos no se pueden fijar: no es un error.
umask 077
mkdir -p "$BACKUP_DIR" || fallar "no se pudo crear la carpeta $BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

inicio=$(date +%s)
nombre="distribuidora-$(date +%Y%m%d-%H%M%S).dump"
final="$BACKUP_DIR/$nombre"
temporal="$final.tmp"
listado=$(mktemp)

limpiar() { rm -f "$temporal" "$listado"; }
trap limpiar EXIT
trap 'limpiar; exit 1' INT TERM

if ! pg_dump -Fc --file="$temporal"; then
  fallar "pg_dump no pudo completar el backup; no se genero archivo"
fi

# Verificacion (D12): el archivo debe poder leerse como backup y traer las tablas de libro.
if ! pg_restore --list "$temporal" > "$listado" 2>/dev/null; then
  mv "$temporal" "$final.fallido"
  fallar "el backup no se pudo leer (pg_restore --list fallo); se guardo como $nombre.fallido y no cuenta como backup valido"
fi
for libro in $LIBROS; do
  if ! grep -q " TABLE public $libro " "$listado"; then
    mv "$temporal" "$final.fallido"
    fallar "al backup le falta la tabla $libro; se guardo como $nombre.fallido y no cuenta como backup valido"
  fi
done

chmod 600 "$temporal" 2>/dev/null || true
mv "$temporal" "$final" || fallar "no se pudo renombrar el backup a $nombre"

# Retencion (D13): despues de un backup verificado, se borran solo los .dump con el formato de
# nombre de los backups que excedan los ultimos N. Todo lo demas (.fallido, .tmp, otros
# nombres) no se toca.
ls -1 "$BACKUP_DIR" | grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$' | sort | head -n "-$BACKUP_RETENCION" |
  while IFS= read -r viejo; do
    rm -f "$BACKUP_DIR/$viejo" && registrar "Retencion: se borro $viejo"
  done

tamano=$(wc -c < "$final" | tr -d ' ')
registrar "Backup verificado: archivo=$nombre tamano=$tamano bytes duracion=$(( $(date +%s) - inicio ))s"
