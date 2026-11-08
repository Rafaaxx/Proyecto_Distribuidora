#!/bin/sh
# Punto de entrada del servicio de backups (change 27a; D10).
#
#   programar.sh          queda en marcha: duerme hasta la proxima BACKUP_HORA (en la zona TZ),
#                         hace el backup y repite cada dia.
#   programar.sh ahora    hace un backup a pedido y termina con el codigo de respaldar.sh.
#
# Variables: BACKUP_HORA (HH:MM, por defecto 03:00), TZ (por defecto America/Argentina/Mendoza),
# ESTADO_DIR (por defecto /tmp/estado-backup; ahi queda la primera corrida programada para la
# verificacion de salud). El resto lo usa respaldar.sh.

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

# Segundos que faltan desde `$2` (segundos de epoch) hasta la proxima ocurrencia de `$1` (HH:MM)
# en la zona TZ. Si ya es esa hora o paso, es la de manana. Se calcula con la fecha local de la
# zona, asi respeta los cambios de hora de verano.
segundos_hasta_proxima() {
  _hora="$1"
  _ahora="$2"
  _hoy=$(date -d "@$_ahora" +%Y-%m-%d)
  _objetivo=$(date -d "$_hoy $_hora" +%s) || return 1
  if [ "$_objetivo" -le "$_ahora" ]; then
    # Se suma el dia a la fecha sola: en "03:00 + 1 day" GNU date leeria "+ 1" como zona horaria.
    _manana=$(date -d "$_hoy + 1 day" +%Y-%m-%d) || return 1
    _objetivo=$(date -d "$_manana $_hora" +%s) || return 1
  fi
  echo $((_objetivo - _ahora))
}

# Con PROGRAMAR_SOLO_FUNCIONES=1 el archivo solo define la funcion (lo usan las pruebas).
if [ "${PROGRAMAR_SOLO_FUNCIONES:-}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

export TZ="${TZ:-America/Argentina/Mendoza}"
BACKUP_HORA="${BACKUP_HORA:-03:00}"
ESTADO_DIR="${ESTADO_DIR:-/tmp/estado-backup}"

if [ "${1:-}" = "ahora" ]; then
  exec sh "$DIR_SCRIPTS/respaldar.sh"
fi

case "$BACKUP_HORA" in
  [01][0-9]:[0-5][0-9]|2[0-3]:[0-5][0-9]) ;;
  *)
    echo "ERROR: BACKUP_HORA debe tener la forma HH:MM entre 00:00 y 23:59 (valor recibido: '$BACKUP_HORA')" >&2
    exit 1
    ;;
esac

mkdir -p "$ESTADO_DIR"
trap 'exit 0' INT TERM

echo "$(date '+%Y-%m-%d %H:%M:%S %z') Servicio de backups en marcha: todos los dias a las $BACKUP_HORA ($TZ)"
primera=true
while true; do
  segundos=$(segundos_hasta_proxima "$BACKUP_HORA" "$(date +%s)") || {
    echo "ERROR: no se pudo calcular la proxima corrida con BACKUP_HORA='$BACKUP_HORA' y TZ='$TZ'" >&2
    exit 1
  }
  if [ "$primera" = true ]; then
    echo $(( $(date +%s) + segundos )) > "$ESTADO_DIR/primera"
    primera=false
  fi
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') Proximo backup en $segundos segundos"
  # `sleep` en segundo plano + `wait`: asi el servicio atiende la senal de parada enseguida.
  sleep "$segundos" &
  wait $!
  # Un backup que falla no detiene el servicio: queda el error en el registro y la salud avisa.
  sh "$DIR_SCRIPTS/respaldar.sh" || true
  # Evita repetir en el mismo segundo si el reloj se atrasa.
  sleep 1
done
