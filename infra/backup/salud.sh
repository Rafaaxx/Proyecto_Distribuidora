#!/bin/sh
# Salud del servicio de backups (change 27a; D14; docs/02 §17). Sale con 0 si esta sano y con 1
# si no. Docker lo corre como verificacion de salud: `docker compose ps` muestra el estado.
#
# No sano cuando:
#   - el .dump valido mas reciente tiene mas de 26 horas; o
#   - no hay ninguno y ya paso la primera hora programada (mas una hora de gracia, para no
#     marcar como enfermo al servicio mientras el primer backup se esta haciendo).
# Los .fallido y .tmp no cuentan. Un backup se considera valido si esta como .dump: solo se
# renombra a ese nombre despues de verificarlo (respaldar.sh).
#
# Variables: BACKUP_DIR (por defecto /backups) y ESTADO_DIR (por defecto /tmp/estado-backup),
# donde programar.sh deja la fecha de la primera corrida programada (archivo `primera`).

BACKUP_DIR="${BACKUP_DIR:-/backups}"
ESTADO_DIR="${ESTADO_DIR:-/tmp/estado-backup}"
LIMITE_MINUTOS=$((26 * 60))
GRACIA_SEGUNDOS=3600

mas_reciente=$(ls -1t "$BACKUP_DIR" 2>/dev/null | grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$' | head -n 1)

if [ -n "$mas_reciente" ]; then
  if [ -n "$(find "$BACKUP_DIR/$mas_reciente" -mmin "-$LIMITE_MINUTOS" 2>/dev/null)" ]; then
    exit 0
  fi
  echo "El ultimo backup valido ($mas_reciente) tiene mas de 26 horas" >&2
  exit 1
fi

# Sin ningun backup valido: sano solo hasta una hora despues de la primera corrida programada.
if [ -r "$ESTADO_DIR/primera" ]; then
  primera=$(cat "$ESTADO_DIR/primera")
  if [ "$(date +%s)" -le $((primera + GRACIA_SEGUNDOS)) ]; then
    exit 0
  fi
  echo "No hay ningun backup valido y ya paso la primera hora programada" >&2
  exit 1
fi

# Todavia no arranco el programador (periodo de inicio): sano.
exit 0
