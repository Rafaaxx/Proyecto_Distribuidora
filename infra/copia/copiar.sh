#!/bin/sh
# Punto de entrada de la copia externa (change 27b; D2, D4, D5, D6, D14).
#
#   copiar.sh                 queda en marcha: una corrida cada COPIA_INTERVALO_SEGUNDOS (3600).
#   copiar.sh ahora           una corrida y termina (0 bien, 1 si algo fallo).
#   copiar.sh bajar ARCHIVO   baja y descifra un backup del destino a BAJADOS_DIR (/bajados).
#
# Una corrida: lista el destino; sube los .dump validos que la retencion local conserva (y que
# la del destino tambien conservaria) y que todavia no estan; comprueba cada uno contra el
# original bajandolo y descifrandolo (rclone check --download); y SOLO si todo salio bien aplica en el
# destino la misma retencion 14 + 8 sobre lo que hay en el destino. Nunca borra en el destino
# porque falte algo en la carpeta local (D2). Variables: ver lib.sh, mas BACKUP_DIR (/backups,
# solo lectura), BACKUP_DIARIOS, BACKUP_SEMANALES y AVISO_URL (opcional, D14).

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BAJADOS_DIR="${BAJADOS_DIR:-/bajados}"
BACKUP_DIARIOS="${BACKUP_DIARIOS:-14}"
BACKUP_SEMANALES="${BACKUP_SEMANALES:-8}"
COPIA_INTERVALO_SEGUNDOS="${COPIA_INTERVALO_SEGUNDOS:-3600}"

. "$DIR_SCRIPTS/lib.sh"
RETENCION_SOLO_FUNCIONES=1 . "$DIR_SCRIPTS/retencion.sh"

for variable in BACKUP_DIARIOS BACKUP_SEMANALES COPIA_INTERVALO_SEGUNDOS; do
  eval "valor=\$$variable"
  case "$valor" in
    ''|*[!0-9]*|0) fallar "$variable debe ser un numero entero mayor que 0 (valor recibido: '$valor')" ;;
  esac
done

# Aviso externo opcional (D14): sin AVISO_URL no hace nada; nunca envia datos del negocio y un
# fallo del aviso no cambia el resultado de la copia.
avisar() {
  [ -n "${AVISO_URL:-}" ] || return 0
  _destino="$AVISO_URL"
  [ "$1" = "fallo" ] && _destino="${AVISO_URL%/}/fail"
  wget -q -T 10 -O /dev/null "$_destino" 2>/dev/null || registrar "AVISO: no se pudo llamar a la direccion de aviso" >&2
  return 0
}

motivo() { tr '\n' ' ' < "$ESTADO_DIR/error" 2>/dev/null | cut -c1-300; }

# Sube un archivo y lo comprueba contra el original. Devuelve 0 si quedo copiado y verificado.
subir() {
  _n="$1"
  rclone copyto "$BACKUP_DIR/$_n" "cifrado:$_n" 2>"$ESTADO_DIR/error" || return 1
  rclone check --download --one-way --include "/$_n" "$BACKUP_DIR" cifrado: 2>"$ESTADO_DIR/error" || return 1
  _t=$(wc -c < "$BACKUP_DIR/$_n" | tr -d ' ')
  registrar "Copia externa verificada: archivo=$_n tamano=$_t bytes"
}

ciclo() {
  _inicio=$(date +%s)
  _remotos=$(listar_destino) || {
    registrar "ERROR: no se pudo leer el destino de la copia externa: $(motivo)" >&2
    avisar fallo
    return 1
  }
  _locales=$(ls -1 "$BACKUP_DIR" 2>/dev/null | grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$')
  _locales_quedan=$(echo "$_locales" | retencion_conservar "$BACKUP_DIARIOS" "$BACKUP_SEMANALES")
  _union_quedan=$(printf '%s\n%s\n' "$_locales" "$_remotos" | grep -v '^$' | retencion_conservar "$BACKUP_DIARIOS" "$BACKUP_SEMANALES")

  _fallo=0
  _subidos=""
  for _n in $_locales_quedan; do
    echo "$_union_quedan" | grep -qx "$_n" || continue
    echo "$_remotos" | grep -qx "$_n" && continue
    if subir "$_n"; then
      _subidos="$_subidos $_n"
    else
      guardar_estado "$(clasificar_error "$(cat "$ESTADO_DIR/error")")"
      registrar "ERROR: no se pudo copiar $_n: $(motivo)" >&2
      _fallo=1
    fi
  done
  if [ "$_fallo" -ne 0 ]; then
    avisar fallo
    return 1
  fi

  # Retencion en el destino (D2): solo despues de una corrida sin errores.
  _en_destino=$(printf '%s\n' "$_remotos"; for _n in $_subidos; do echo "$_n"; done)
  echo "$_en_destino" | grep -v '^$' | retencion_sobrantes "$BACKUP_DIARIOS" "$BACKUP_SEMANALES" |
    while IFS= read -r _viejo; do
      rclone deletefile "cifrado:$_viejo" 2>/dev/null && registrar "Retencion en el destino: se borro $_viejo"
    done

  _mas_reciente=$(echo "$_en_destino" | grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$' | LC_ALL=C sort | tail -n 1)
  [ -z "$_mas_reciente" ] || echo "$_mas_reciente" > "$ESTADO_DIR/ultimo_destino"
  guardar_estado ok
  registrar "Corrida de copia externa terminada: subidos=$(echo $_subidos | wc -w | tr -d ' ') duracion=$(( $(date +%s) - _inicio ))s"
  avisar bien
  return 0
}

bajar() {
  _archivo="$1"
  case "$_archivo" in
    distribuidora-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9].dump) ;;
    *) fallar "el nombre debe ser del tipo distribuidora-AAAAMMDD-HHMMSS.dump (recibido: '$_archivo')" ;;
  esac
  mkdir -p "$BAJADOS_DIR" || fallar "no se pudo crear $BAJADOS_DIR"
  _remotos=$(listar_destino) || fallar "no se pudo leer el destino: $(motivo)"
  echo "$_remotos" | grep -qx "$_archivo" || fallar "$_archivo no esta en el destino"
  _tmp="$BAJADOS_DIR/$_archivo.tmp"
  if ! rclone copyto "cifrado:$_archivo" "$_tmp" 2>"$ESTADO_DIR/error"; then
    rm -f "$_tmp"
    fallar "no se pudo bajar $_archivo (revise la clave de cifrado): $(motivo)"
  fi
  mv "$_tmp" "$BAJADOS_DIR/$_archivo" || { rm -f "$_tmp"; fallar "no se pudo guardar $_archivo"; }
  registrar "Backup bajado y descifrado: archivo=$_archivo tamano=$(wc -c < "$BAJADOS_DIR/$_archivo" | tr -d ' ') bytes carpeta=$BAJADOS_DIR"
}

case "${1:-}" in
  ahora)
    ciclo
    exit $?
    ;;
  bajar)
    [ -n "${2:-}" ] || fallar "uso: bajar <archivo>"
    bajar "$2"
    exit 0
    ;;
  '') ;;
  *) fallar "uso: copiar.sh [ahora | bajar <archivo>]" ;;
esac

trap 'exit 0' INT TERM
date +%s > "$ESTADO_DIR/inicio"
registrar "Servicio de copia externa en marcha: cada $COPIA_INTERVALO_SEGUNDOS segundos"
while true; do
  ciclo || true
  sleep "$COPIA_INTERVALO_SEGUNDOS" &
  wait $!
done
