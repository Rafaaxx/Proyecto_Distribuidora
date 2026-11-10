#!/bin/sh
# Salud de la copia externa (change 27b; D6; docs/02 §17). 0 sano, 1 no sano.
#
# No sano cuando:
#   - la ultima corrida fallo por credenciales/acceso al destino o por la clave de cifrado
#     (un corte de internet NO cuenta: es transitorio y lo cubre el limite de antiguedad); o
#   - el backup mas reciente que llego al destino (por la fecha de su nombre) tiene mas de 26
#     horas; o
#   - no hay ninguno y ya paso la primera hora desde que arranco el servicio.
# Mira el destino en el momento; si no puede (sin internet), usa el ultimo que vio.

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
. "$DIR_SCRIPTS/lib.sh"
LIMITE_SEGUNDOS=$((26 * 3600))
GRACIA_SEGUNDOS=3600

if [ "$(cat "$ESTADO_DIR/estado" 2>/dev/null)" = "acceso" ]; then
  echo "La ultima corrida fallo por las credenciales o la configuracion del destino" >&2
  exit 1
fi

if _lista=$(listar_destino 2>/dev/null); then
  _mas_reciente=$(echo "$_lista" | grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$' | LC_ALL=C sort | tail -n 1)
  [ -z "$_mas_reciente" ] || echo "$_mas_reciente" > "$ESTADO_DIR/ultimo_destino"
else
  if [ "$(cat "$ESTADO_DIR/estado" 2>/dev/null)" = "clave" ]; then
    echo "La clave de cifrado no abre los archivos del destino" >&2
    exit 1
  fi
  _mas_reciente=$(cat "$ESTADO_DIR/ultimo_destino" 2>/dev/null)
fi

if [ -n "$_mas_reciente" ]; then
  _fecha=${_mas_reciente#distribuidora-}
  _dia=${_fecha%%-*}
  _resto=${_fecha#*-}
  _hora=${_resto%.dump}
  _iso="$(echo "$_dia" | cut -c1-4)-$(echo "$_dia" | cut -c5-6)-$(echo "$_dia" | cut -c7-8)"
  _momento=$(date -d "$_iso $(echo "$_hora" | cut -c1-2):$(echo "$_hora" | cut -c3-4):$(echo "$_hora" | cut -c5-6)" +%s) || exit 1
  if [ $(( $(date +%s) - _momento )) -le "$LIMITE_SEGUNDOS" ]; then
    exit 0
  fi
  echo "El backup mas reciente del destino ($_mas_reciente) tiene mas de 26 horas" >&2
  exit 1
fi

# Sin ningun backup en el destino: sano solo durante la primera hora de vida del servicio.
if [ -r "$ESTADO_DIR/inicio" ]; then
  if [ "$(date +%s)" -le $(( $(cat "$ESTADO_DIR/inicio") + GRACIA_SEGUNDOS )) ]; then
    exit 0
  fi
  echo "No hay ningun backup en el destino y ya paso la primera hora" >&2
  exit 1
fi
exit 0
