#!/bin/sh
# Funciones comunes de la copia externa (change 27b; D4, D5, D6). Se carga con `.` desde
# copiar.sh y salud.sh.
#
# Configuracion de rclone SOLO por variables (sin archivo): el destino "bruto" es lo que ve el
# proveedor y "cifrado" es la vista descifrada (crypt: nombres y contenido cifrados).
#   COPIA_TIPO            s3 | local   (local: carpeta del equipo, para ensayar sin cuenta)
#   COPIA_RUTA            s3: cubo (y carpeta opcional, cubo/carpeta); local: ruta absoluta
#   COPIA_S3_PROVEEDOR    proveedor S3 de rclone (por defecto Other)
#   COPIA_S3_ENDPOINT     direccion del servicio S3 (obligatoria con s3)
#   COPIA_S3_REGION       region (opcional)
#   COPIA_ACCESS_KEY_ID, COPIA_SECRET_ACCESS_KEY   credenciales del cubo (con s3)
#   COPIA_CLAVE_CIFRADO, COPIA_SAL_CIFRADO         ya "ofuscadas" con `rclone obscure`
#   ESTADO_DIR            estado para la salud (por defecto /tmp/estado-copia)
#   TZ                    zona horaria de los nombres de los backups

ESTADO_DIR="${ESTADO_DIR:-/tmp/estado-copia}"
export TZ="${TZ:-America/Argentina/Mendoza}"

registrar() { echo "$(date '+%Y-%m-%d %H:%M:%S %z') $*"; }
fallar() { registrar "ERROR: $*" >&2; exit 1; }

# Opciones de red: sin internet la corrida falla rapido y la siguiente reintenta.
export RCLONE_CONFIG=/tmp/rclone-sin-archivo.conf
export RCLONE_RETRIES=2 RCLONE_LOW_LEVEL_RETRIES=2 RCLONE_CONTIMEOUT=10s RCLONE_TIMEOUT=30s
: > "$RCLONE_CONFIG" 2>/dev/null || true

for _v in COPIA_TIPO COPIA_RUTA COPIA_CLAVE_CIFRADO COPIA_SAL_CIFRADO; do
  eval "_valor=\$$_v"
  [ -n "$_valor" ] || fallar "falta la variable $_v"
done

case "$COPIA_TIPO" in
  local)
    export RCLONE_CONFIG_BRUTO_TYPE=local
    ;;
  s3)
    for _v in COPIA_S3_ENDPOINT COPIA_ACCESS_KEY_ID COPIA_SECRET_ACCESS_KEY; do
      eval "_valor=\$$_v"
      [ -n "$_valor" ] || fallar "con COPIA_TIPO=s3 falta la variable $_v"
    done
    export RCLONE_CONFIG_BRUTO_TYPE=s3
    export RCLONE_CONFIG_BRUTO_PROVIDER="${COPIA_S3_PROVEEDOR:-Other}"
    export RCLONE_CONFIG_BRUTO_ENDPOINT="$COPIA_S3_ENDPOINT"
    export RCLONE_CONFIG_BRUTO_REGION="${COPIA_S3_REGION:-}"
    export RCLONE_CONFIG_BRUTO_ACCESS_KEY_ID="$COPIA_ACCESS_KEY_ID"
    export RCLONE_CONFIG_BRUTO_SECRET_ACCESS_KEY="$COPIA_SECRET_ACCESS_KEY"
    export RCLONE_CONFIG_BRUTO_ENV_AUTH=false
    # Nunca crea cubos: si el cubo no existe es un error de configuracion, no algo que arreglar.
    export RCLONE_CONFIG_BRUTO_NO_CHECK_BUCKET=true
    ;;
  *) fallar "COPIA_TIPO debe ser s3 o local (valor recibido: '$COPIA_TIPO')" ;;
esac

export RCLONE_CONFIG_CIFRADO_TYPE=crypt
export RCLONE_CONFIG_CIFRADO_REMOTE="bruto:$COPIA_RUTA"
export RCLONE_CONFIG_CIFRADO_PASSWORD="$COPIA_CLAVE_CIFRADO"
export RCLONE_CONFIG_CIFRADO_PASSWORD2="$COPIA_SAL_CIFRADO"
export RCLONE_CONFIG_CIFRADO_FILENAME_ENCRYPTION=standard
export RCLONE_CONFIG_CIFRADO_DIRECTORY_NAME_ENCRYPTION=true

mkdir -p "$ESTADO_DIR" 2>/dev/null || true

# Guarda el estado de la ultima corrida: ok | acceso | clave | red (lo lee salud.sh).
guardar_estado() { echo "$1" > "$ESTADO_DIR/estado" 2>/dev/null || true; }

# Distingue un fallo de credenciales o de configuracion del destino (persistente) de uno de red
# (transitorio), mirando el texto del error de rclone.
clasificar_error() {
  case "$(echo "$1" | tr 'A-Z' 'a-z')" in
    *denied*|*forbidden*|*unauthori*|*invalidaccesskey*|*signaturedoesnotmatch*|*credential*|*authenticat*|*nosuchbucket*|*"status code: 40"[13]*) echo acceso ;;
    *) echo red ;;
  esac
}

# Imprime los nombres (descifrados) de los archivos del destino. Devuelve 0 si pudo listar (un
# destino todavia vacio o inexistente es una lista vacia), 1 si no pudo; en ese caso guarda el
# estado (acceso, clave o red) y deja el motivo en $ESTADO_DIR/error. Si el destino tiene
# archivos pero la clave no abre ninguno, es la clave equivocada.
listar_destino() {
  _err="$ESTADO_DIR/error"
  _lista=$(rclone lsf cifrado: --files-only 2>"$_err"); _rc=$?
  if [ "$_rc" -eq 3 ]; then _lista=""; _rc=0; fi
  if [ "$_rc" -ne 0 ]; then
    guardar_estado "$(clasificar_error "$(cat "$_err")")"
    return 1
  fi
  if [ -z "$_lista" ]; then
    _crudo=$(rclone lsf "bruto:$COPIA_RUTA" --files-only 2>/dev/null | head -n 1)
    if [ -n "$_crudo" ]; then
      echo "la clave de cifrado no abre ningun archivo del destino" > "$_err"
      guardar_estado clave
      return 1
    fi
  fi
  [ -z "$_lista" ] || echo "$_lista"
  return 0
}
