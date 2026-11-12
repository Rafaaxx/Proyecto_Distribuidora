/**
 * Número propuesto de la venta (change 18a, tarea 12.1; `design.md` D4; VTA-06, ADR-008).
 * La pantalla propone `PPP-NNNNNN`: el mayor entre el último correlativo del servidor y el
 * guardado en el navegador, más uno. El servidor valida igual y, ante `NUMERO_DUPLICADO`, la
 * pantalla relee la numeración. El almacenamiento del navegador puede no existir o fallar
 * (ventana privada, datos bloqueados): toda lectura y escritura va en `try/catch` y la pantalla
 * funciona igual sin él.
 */

/** Lo mínimo que se usa de `Storage`; permite inyectar uno en memoria en las pruebas. */
export interface AlmacenDeCorrelativo {
  getItem(clave: string): string | null
  setItem(clave: string, valor: string): void
}

export interface NumeracionDelServidor {
  prefijo: string
  ultimoCorrelativo: number
}

const PATRON_DE_NUMERO = /^(.+)-(\d+)$/
const DIGITOS_MINIMOS = 6

function claveDeAlmacenamiento(prefijo: string): string {
  return `ventas.correlativo.${prefijo}`
}

/** `formatearNumero('V01', 42)` es `"V01-000042"`. */
export function formatearNumero(prefijo: string, correlativo: number): string {
  return `${prefijo}-${String(correlativo).padStart(DIGITOS_MINIMOS, '0')}`
}

/** Correlativo de un número con el prefijo del dispositivo; `null` si no es de ese dispositivo o no es válido. */
export function correlativoDeNumero(numero: string, prefijo: string): number | null {
  const coincidencia = PATRON_DE_NUMERO.exec(numero)
  if (coincidencia === null || coincidencia[1] !== prefijo) return null
  const correlativo = Number(coincidencia[2])
  return Number.isSafeInteger(correlativo) ? correlativo : null
}

/** El mayor entre el servidor y el navegador, más uno. */
export function proponerNumero(servidor: NumeracionDelServidor, guardado: number | null): string {
  const mayor = Math.max(servidor.ultimoCorrelativo, guardado ?? 0)
  return formatearNumero(servidor.prefijo, mayor + 1)
}

/** El almacenamiento local del navegador, o `undefined` si no se puede ni nombrar. */
export function almacenDelNavegador(): AlmacenDeCorrelativo | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage
  } catch {
    return undefined
  }
}

/**
 * Último correlativo guardado para el prefijo; `null` si no hay, está corrupto, el acceso falla o
 * no hay almacenamiento (`undefined`). Quien llama pasa `almacenDelNavegador()`.
 */
export function leerCorrelativoGuardado(
  prefijo: string,
  almacen: AlmacenDeCorrelativo | undefined,
): number | null {
  try {
    const crudo = almacen?.getItem(claveDeAlmacenamiento(prefijo)) ?? null
    if (crudo === null || !/^\d+$/.test(crudo)) return null
    const valor = Number(crudo)
    return Number.isSafeInteger(valor) ? valor : null
  } catch {
    return null
  }
}

/** Guarda el correlativo usado; nunca retrocede (conserva el mayor) y nunca lanza. */
export function guardarCorrelativo(
  prefijo: string,
  correlativo: number,
  almacen: AlmacenDeCorrelativo | undefined,
): void {
  try {
    const actual = leerCorrelativoGuardado(prefijo, almacen) ?? 0
    almacen?.setItem(claveDeAlmacenamiento(prefijo), String(Math.max(actual, correlativo)))
  } catch {
    // Sin almacenamiento la pantalla funciona igual: el servidor es la fuente (D4).
  }
}

/**
 * Número que se propone después de `NUMERO_DUPLICADO` (D4): el siguiente al mayor entre el
 * servidor recién releído, el navegador y el número que acaba de fallar.
 */
export function proponerTrasDuplicado(
  servidor: NumeracionDelServidor,
  guardado: number | null,
  intentado: string,
): string {
  const fallido = correlativoDeNumero(intentado, servidor.prefijo) ?? 0
  return proponerNumero({ prefijo: servidor.prefijo, ultimoCorrelativo: Math.max(servidor.ultimoCorrelativo, fallido) }, guardado)
}
