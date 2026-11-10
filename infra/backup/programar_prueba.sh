#!/bin/sh
# Punto de entrada del servicio de prueba de restauracion (change 27b; D10; docs/02 §16.2).
#
#   programar_prueba.sh                 queda en marcha: una vez por mes, el dia PRUEBA_DIA a la
#                                       hora PRUEBA_HORA (en la zona TZ) hace la prueba.
#   programar_prueba.sh ahora [ARCHIVO] hace una prueba a pedido (el backup mas reciente o el
#                                       indicado) y termina con el codigo de probar_restauracion.sh.
#
# Variables: PRUEBA_DIA (1 a 31, por defecto 1; en un mes mas corto se usa el ultimo dia),
# PRUEBA_HORA (HH:MM, por defecto 04:00), TZ (por defecto America/Argentina/Mendoza),
# ESTADO_DIR (por defecto /estado-prueba; ahi quedan la ultima prueba y la hora de arranque
# para la verificacion de salud). El resto lo usa probar_restauracion.sh.

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

# Fecha epoch del dia $2 (se acota al ultimo dia del mes) de $1 (YYYY-MM) a la hora $3 (HH:MM).
_objetivo_del_mes() {
  _ultimo=$(date -d "$1-01 + 1 month - 1 day" +%d) || return 1
  _ultimo=${_ultimo#0}
  _d=$2
  [ "$_d" -le "$_ultimo" ] || _d=$_ultimo
  date -d "$1-$(printf '%02d' "$_d") $3" +%s
}

# Segundos que faltan desde `$3` (epoch) hasta la proxima ocurrencia del dia `$1` a la hora `$2`
# en la zona TZ: este mes si todavia no llego (y no es justo la hora), si no, el mes que viene.
# Se calcula con la fecha local de la zona, asi respeta los cambios de hora de verano.
segundos_hasta_proxima_prueba() {
  _mes=$(date -d "@$3" +%Y-%m) || return 1
  _candidato=$(_objetivo_del_mes "$_mes" "$1" "$2") || return 1
  if [ "$_candidato" -le "$3" ]; then
    _mes=$(date -d "$_mes-01 + 1 month" +%Y-%m) || return 1
    _candidato=$(_objetivo_del_mes "$_mes" "$1" "$2") || return 1
  fi
  echo $((_candidato - $3))
}

# Con PROGRAMAR_PRUEBA_SOLO_FUNCIONES=1 el archivo solo define las funciones (lo usan las pruebas).
if [ "${PROGRAMAR_PRUEBA_SOLO_FUNCIONES:-}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

export TZ="${TZ:-America/Argentina/Mendoza}"
PRUEBA_DIA="${PRUEBA_DIA:-1}"
PRUEBA_HORA="${PRUEBA_HORA:-04:00}"
ESTADO_DIR="${ESTADO_DIR:-/estado-prueba}"

case "$PRUEBA_DIA" in
  ''|*[!0-9]*)
    echo "ERROR: PRUEBA_DIA debe ser un numero entero de 1 a 31 (valor recibido: '$PRUEBA_DIA')" >&2
    exit 1
    ;;
esac
if [ "$PRUEBA_DIA" -lt 1 ] || [ "$PRUEBA_DIA" -gt 31 ]; then
  echo "ERROR: PRUEBA_DIA debe ser un numero entero de 1 a 31 (valor recibido: '$PRUEBA_DIA')" >&2
  exit 1
fi
case "$PRUEBA_HORA" in
  [01][0-9]:[0-5][0-9]|2[0-3]:[0-5][0-9]) ;;
  *)
    echo "ERROR: PRUEBA_HORA debe tener la forma HH:MM entre 00:00 y 23:59 (valor recibido: '$PRUEBA_HORA')" >&2
    exit 1
    ;;
esac

if [ "${1:-}" = "ahora" ]; then
  shift
  exec sh "$DIR_SCRIPTS/probar_restauracion.sh" "$@"
fi

mkdir -p "$ESTADO_DIR"
# Hora de arranque del servicio: la salud la usa mientras todavia no hubo ninguna prueba.
[ -f "$ESTADO_DIR/inicio" ] || date +%s > "$ESTADO_DIR/inicio"
trap 'exit 0' INT TERM

echo "$(date '+%Y-%m-%d %H:%M:%S %z') Servicio de prueba de restauracion en marcha: el dia $PRUEBA_DIA de cada mes a las $PRUEBA_HORA ($TZ)"
while true; do
  segundos=$(segundos_hasta_proxima_prueba "$PRUEBA_DIA" "$PRUEBA_HORA" "$(date +%s)") || {
    echo "ERROR: no se pudo calcular la proxima prueba con PRUEBA_DIA='$PRUEBA_DIA', PRUEBA_HORA='$PRUEBA_HORA' y TZ='$TZ'" >&2
    exit 1
  }
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') Proxima prueba de restauracion en $segundos segundos"
  # `sleep` en segundo plano + `wait`: asi el servicio atiende la senal de parada enseguida.
  sleep "$segundos" &
  wait $!
  # Una prueba que falla no detiene el servicio: queda el error en el registro y la salud avisa.
  sh "$DIR_SCRIPTS/probar_restauracion.sh" || true
  # Evita repetir en el mismo minuto si el reloj se atrasa.
  sleep 61
done
