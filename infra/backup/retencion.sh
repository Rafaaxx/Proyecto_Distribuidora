#!/bin/sh
# Regla de retencion de backups (change 27b; D1; docs/02 §16.2). Funciones de shell puras: sin
# tocar archivos, reciben nombres por la entrada estandar.
#
#   retencion_conservar DIARIOS SEMANALES   imprime (ordenados) los nombres que se conservan
#   retencion_sobrantes DIARIOS SEMANALES   imprime los nombres validos que se pueden borrar
#
# Se conserva el backup mas reciente de cada uno de los DIARIOS dias mas recientes que tienen
# backup, y el mas reciente de cada una de las SEMANALES semanas mas recientes que tienen backup
# (semana de lunes a domingo). Un mismo archivo puede contar como diario y semanal. El dia y la
# semana salen del nombre (distribuidora-AAAAMMDD-HHMMSS.dump), no de la fecha del archivo. Se
# cuentan dias y semanas CON backup, no del calendario: si los backups se detienen, no se borra
# nada mas. Los nombres que no siguen el formato se ignoran. El mismo script usan las imagenes
# de backup y de copia externa.
#
# Con RETENCION_SOLO_FUNCIONES=1 el archivo solo define las funciones (lo usan las pruebas y
# respaldar.sh).

_retencion_validos() {
  grep -E '^distribuidora-[0-9]{8}-[0-9]{6}\.dump$' | LC_ALL=C sort -u
}

retencion_conservar() {
  _diarios="$1"
  _semanales="$2"
  _validos=$(_retencion_validos)
  [ -n "$_validos" ] || return 0
  # Linea por nombre: "nombre dia semana ISO" (la semana ISO va de lunes a domingo).
  echo "$_validos" | while IFS= read -r _n; do
    _d=${_n#distribuidora-}
    _d=${_d%%-*}
    _iso="$(echo "$_d" | cut -c1-4)-$(echo "$_d" | cut -c5-6)-$(echo "$_d" | cut -c7-8)"
    echo "$_n $_d $(date -d "$_iso" +%G-%V)"
  done | awk -v D="$_diarios" -v S="$_semanales" '
    {
      ultimo_dia[$2] = $1; ultima_sem[$3] = $1
      if (!($2 in vd)) { vd[$2] = 1; dias[++nd] = $2 }
      if (!($3 in vs)) { vs[$3] = 1; sems[++ns] = $3 }
    }
    END {
      for (i = nd; i > 0 && nd - i < D; i--) conservar[ultimo_dia[dias[i]]] = 1
      for (i = ns; i > 0 && ns - i < S; i--) conservar[ultima_sem[sems[i]]] = 1
      for (n in conservar) print n
    }' | LC_ALL=C sort
}

retencion_sobrantes() {
  _todos=$(_retencion_validos)
  [ -n "$_todos" ] || return 0
  _quedan=$(echo "$_todos" | retencion_conservar "$1" "$2")
  echo "$_todos" | while IFS= read -r _n; do
    echo "$_quedan" | grep -qx "$_n" || echo "$_n"
  done
}

if [ "${RETENCION_SOLO_FUNCIONES:-}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

echo "retencion.sh define funciones; cargalo con RETENCION_SOLO_FUNCIONES=1" >&2
exit 1
