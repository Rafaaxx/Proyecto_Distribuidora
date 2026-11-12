#!/bin/sh
# Comprueba una base restaurada contra el archivo del que salio (change 27b; D9; docs/00 §9
# criterio 12; INV-05). Uso: comprobar.sh ARCHIVO   (conexion por las variables PG*)
#
# Tabla por tabla, la cantidad de filas que trae el archivo (leyendo sus datos con pg_restore)
# debe ser igual a la que quedo en la base; el rol de la aplicacion (`app_runtime`) no debe poder
# UPDATE ni DELETE en las cuatro tablas de libro; y debe existir la version de migraciones
# (alembic_version con una fila). Si algo no coincide, sale con 1 nombrando la tabla; nunca
# imprime datos del negocio.

DIR_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
. "$DIR_SCRIPTS/lib_restaurar.sh"

[ -n "${1:-}" ] || fallar "uso: comprobar.sh ARCHIVO"
archivo=$(resolver_archivo "$1") || exit 1

tmp=$(mktemp -d) || fallar "no se pudo crear una carpeta temporal"
trap 'rm -rf "$tmp"' EXIT

# Tablas con datos del archivo (todas, aunque esten vacias) y filas que trae cada una.
pg_restore --list "$archivo" | sed -n 's/.* TABLE DATA public \([^ ]*\) .*/\1/p' > "$tmp/nombres"
pg_restore --data-only -f - "$archivo" 2>"$tmp/error" | awk -v nombres="$tmp/nombres" '
  BEGIN { while ((getline linea < nombres) > 0) n[linea] = 0 }
  dentro { if ($0 == "\\.") dentro = 0; else n[tabla]++; next }
  /^COPY / { tabla = $2; sub(/^public\./, "", tabla); gsub(/"/, "", tabla); dentro = 1 }
  END { for (t in n) print t, n[t] }' | sort > "$tmp/archivo"
[ -s "$tmp/archivo" ] || fallar "no se pudieron leer los datos del archivo: $(tr '\n' ' ' < "$tmp/error" | cut -c1-200)"

# Filas de cada tabla de la base (count(*) por tabla, calculado en la base).
consultar "SELECT tablename, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from public.%I', tablename), false, true, '')))[1]::text FROM pg_tables WHERE schemaname = 'public' ORDER BY 1" \
  | tr '|' ' ' | sort > "$tmp/base" || fallar "no se pudo contar las filas de la base"

errores=0
awk -v f="$tmp/archivo" '
  BEGIN { while ((getline linea < f) > 0) { split(linea, p, " "); a[p[1]] = p[2]; visto[p[1]] = 1 } }
  { visto[$1] = 1; b[$1] = $2 }
  END {
    for (t in visto) {
      if (!(t in a)) print "la tabla " t " esta en la base pero no en el archivo"
      else if (!(t in b)) print "la tabla " t " esta en el archivo y no quedo en la base"
      else if (a[t] != b[t]) print "la tabla " t " tiene " b[t] " filas y el archivo trae " a[t]
    }
  }' "$tmp/base" | sort > "$tmp/diferencias"
if [ -s "$tmp/diferencias" ]; then
  while read -r linea; do registrar "ERROR: $linea" >&2; done < "$tmp/diferencias"
  errores=1
fi

# INV-05: la aplicacion no puede modificar ni borrar libros.
if [ "$(consultar "SELECT count(*) FROM pg_roles WHERE rolname = 'app_runtime'")" != "1" ]; then
  registrar "ERROR: no existe el rol app_runtime en la base" >&2
  errores=1
else
  for libro in $LIBROS; do
    for operacion in UPDATE DELETE; do
      if [ "$(consultar "SELECT has_table_privilege('app_runtime', 'public.$libro', '$operacion')")" = "t" ]; then
        registrar "ERROR: app_runtime puede hacer $operacion sobre $libro (INV-05)" >&2
        errores=1
      fi
    done
  done
fi

# La version de migraciones debe estar.
versiones=$(consultar "SELECT count(*) FROM public.alembic_version" 2>/dev/null)
if [ "${versiones:-0}" -lt 1 ] 2>/dev/null; then
  registrar "ERROR: falta la version de migraciones en alembic_version" >&2
  errores=1
fi

[ "$errores" -eq 0 ] || exit 1
tablas=$(wc -l < "$tmp/archivo" | tr -d ' ')
filas=$(awk '{ s += $2 } END { print s + 0 }' "$tmp/archivo")
registrar "Comprobacion correcta: $tablas tablas, $filas filas"
