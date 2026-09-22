/**
 * Huella canónica del contenido de un comando (ADR-012, extensión
 * 2026-09-21; `design.md` D1; `02` §6.2).
 *
 * Implementa JCS (RFC 8785, JSON Canonicalization Scheme) acotado a las
 * formas de dato que el contenido de un comando puede tener: objetos,
 * arreglos, cadenas, enteros JSON, booleanos y `null`. El dominio prohíbe
 * números de punto flotante en todo el sistema (`CLAUDE.md` §4, INV-03),
 * así que esta función deliberadamente no implementa el algoritmo de
 * serialización de `double` de ECMA-262 que exige JCS para números
 * fraccionarios -- ese caso no puede ocurrir en contenido válido.
 *
 * Los importes, costos y porcentajes **no** tienen un tipo dedicado acá:
 * viajan como `string`, ya formateados a la escala de su columna por quien
 * arma el contenido (`redondearImporte(...).toFixed(2)` /
 * `redondearCosto(...).toFixed(6)` de `src/lib/money.ts`, la única fuente
 * de redondeo del frontend, `CLAUDE.md` §4). No se acepta un `Importe`
 * (decimal.js) como tipo de entrada a propósito: decimal.js normaliza su
 * representación interna y **no** preserva los ceros a la derecha con los
 * que se construyó (`new Decimal("31250.00").decimalPlaces()` da `0`, no
 * `2`), a diferencia del `Decimal` de Python, que sí preserva la escala de
 * construcción. Dejar que cada lenguaje formatee explícitamente con su
 * propia librería de dinero antes de entrar a esta función es la única
 * forma de que Python y TypeScript produzcan el mismo texto -- y por lo
 * tanto la misma huella -- para el mismo importe.
 *
 * Debe producir exactamente los mismos bytes canónicos -- y por lo tanto
 * la misma huella SHA-256 -- que `backend/app/commands/huella.py` para el
 * mismo contenido lógico. Los fixtures compartidos de
 * `shared/fixtures/calculo/huella-canonica.json` verifican esta paridad
 * en ambos lenguajes.
 *
 * Reglas de canonización -- ver el docstring de `huella.py` para el
 * detalle completo, es la misma especificación en ambos lados:
 * - Objetos: miembros ordenados por comparación de cadena estándar de
 *   JavaScript (unidades de código UTF-16), recursivo.
 * - Arreglos: conservan su orden original.
 * - Cadenas: normalizadas a NFC, escapadas solo lo estrictamente
 *   necesario (comilla, backslash, controles); el resto -- incluido texto
 *   no-ASCII y emoji -- se emite tal cual.
 * - Los importes y costos/porcentajes viajan como `string`, ya formateados
 *   a la escala de su columna por `src/lib/money.ts` antes de llegar acá
 *   (ver más arriba). Esta función no distingue un `string` "decimal" de
 *   cualquier otro `string`: los serializa igual, con NFC y el mismo
 *   escape.
 * - Una clave con valor `null` y una clave ausente producen huellas
 *   distintas.
 * - Sin espacios en los separadores `,` y `:`.
 *
 * `calcularHuella` es la única función pública de este módulo y su firma
 * tiene un único parámetro (`contenido`): no existe ningún canal para
 * pasarle una huella informada por otro origen, así que el cliente nunca
 * puede fabricar una huella que el servidor "confíe" -- el servidor
 * siempre recalcula la suya con el mismo algoritmo (escenario "La huella
 * informada por el cliente se ignora", spec `sistema/pipeline-de-comandos`).
 */

/** Tipos de dato admitidos en el contenido de un comando. Sin `any`. */
export type ContenidoComando =
  | null
  | boolean
  | number
  | string
  | ContenidoComando[]
  | { [clave: string]: ContenidoComando }

const ESCAPES_CORTOS: Record<string, string> = {
  '\\': '\\\\',
  '"': '\\"',
  '\b': '\\b',
  '\f': '\\f',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
}

function escaparString(valor: string): string {
  const normalizado = valor.normalize('NFC')
  let resultado = '"'
  for (const caracter of normalizado) {
    const codigo = caracter.codePointAt(0) ?? 0
    if (caracter in ESCAPES_CORTOS) {
      resultado += ESCAPES_CORTOS[caracter]
    } else if (codigo < 0x20) {
      resultado += `\\u${codigo.toString(16).padStart(4, '0')}`
    } else {
      resultado += caracter
    }
  }
  return resultado + '"'
}

function serializar(valor: ContenidoComando): string {
  if (valor === null) return 'null'
  if (typeof valor === 'boolean') return valor ? 'true' : 'false'
  if (typeof valor === 'number') {
    if (!Number.isInteger(valor)) {
      throw new TypeError(
        `Número no entero en el contenido de un comando: ${String(valor)} ` +
          '(INV-03: los importes y porcentajes viajan como string, nunca como number fraccionario)',
      )
    }
    return String(valor)
  }
  if (typeof valor === 'string') return escaparString(valor)
  if (Array.isArray(valor)) {
    return '[' + valor.map(serializar).join(',') + ']'
  }
  if (typeof valor === 'object') {
    const entradas = Object.entries(valor as Record<string, ContenidoComando>).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0,
    )
    const miembros = entradas.map(([clave, elemento]) => `${escaparString(clave)}:${serializar(elemento)}`)
    return '{' + miembros.join(',') + '}'
  }
  throw new TypeError(`Tipo no admitido en el contenido de un comando: ${typeof valor}`)
}

function aHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

/**
 * Calcula la huella SHA-256 canónica del contenido de un comando.
 *
 * El resultado es determinista: el mismo contenido lógico produce siempre
 * la misma huella hexadecimal, sin importar el orden de las claves con el
 * que llegó ni el proceso (Python o TypeScript) que lo calculó, siempre
 * que los importes y costos/porcentajes ya vengan formateados como string
 * a la escala de su columna por el llamador (`src/lib/money.ts`).
 */
export async function calcularHuella(
  contenido: Record<string, ContenidoComando>,
): Promise<string> {
  const canonico = serializar(contenido)
  const bytes = new TextEncoder().encode(canonico)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return aHex(digest)
}
