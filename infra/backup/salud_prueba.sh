#!/bin/sh
# Salud del servicio de prueba de restauracion (change 27b; D10; docs/02 §17). Sale con 0 si
# esta sano y con 1 si no.
#
# No sano cuando:
#   - la ultima prueba fallo; o
#   - la ultima prueba buena tiene mas de 35 dias; o
#   - todavia no hubo ninguna y el servicio arranco hace mas de 35 dias.
#
# Variable: ESTADO_DIR (por defecto /estado-prueba), donde probar_restauracion.sh deja `ultimo`
# y `ultima_buena` y programar_prueba.sh deja `inicio`.

ESTADO_DIR="${ESTADO_DIR:-/estado-prueba}"
LIMITE_SEGUNDOS=$((35 * 86400))
ahora=$(date +%s)

if [ "$(cat "$ESTADO_DIR/ultimo" 2>/dev/null)" = "fallo" ]; then
  echo "La ultima prueba de restauracion fallo" >&2
  exit 1
fi

if [ -r "$ESTADO_DIR/ultima_buena" ]; then
  if [ $((ahora - $(cat "$ESTADO_DIR/ultima_buena"))) -le "$LIMITE_SEGUNDOS" ]; then
    exit 0
  fi
  echo "La ultima prueba de restauracion buena tiene mas de 35 dias" >&2
  exit 1
fi

# Ninguna prueba todavia: sano hasta 35 dias despues de que arranco el servicio.
if [ -r "$ESTADO_DIR/inicio" ]; then
  if [ $((ahora - $(cat "$ESTADO_DIR/inicio"))) -le "$LIMITE_SEGUNDOS" ]; then
    exit 0
  fi
  echo "No hubo ninguna prueba de restauracion en mas de 35 dias" >&2
  exit 1
fi

# Todavia no arranco el programador (periodo de inicio): sano.
exit 0
