/**
 * Cantidades de stock en cajas + unidades (CAT-08, INV-04; change 09, tarea 8.3
 * y 8.4). Las cantidades viajan y se guardan en unidad base entera; acá solo se
 * convierte para escribirlas y mostrarlas, con aritmética entera y sin `number`
 * fraccionarios. Lógica pura, sin React.
 */

/** Rango de `integer` de PostgreSQL (INV-04). */
const ENTERO_MAXIMO = 2_147_483_647

export class CantidadInvalidaError extends Error {
  readonly codigo = 'CANTIDAD_INVALIDA'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'CantidadInvalidaError'
  }
}

function entero(valor: number, nombre: string): number {
  if (!Number.isSafeInteger(valor) || valor < 0) {
    throw new CantidadInvalidaError(`${nombre} tiene que ser un entero mayor o igual a cero.`)
  }
  return valor
}

/**
 * `cajas * unidadesPorCaja + unidades`. Sin presentación de referencia
 * (`unidadesPorCaja === null`) solo cuentan las unidades. Lanza
 * `CantidadInvalidaError` si alguna parte no es un entero no negativo o si el
 * resultado no entra en un entero de 32 bits.
 */
export function aUnidadesBase(cajas: number, unidades: number, unidadesPorCaja: number | null): number {
  const c = entero(cajas, 'Las cajas')
  const u = entero(unidades, 'Las unidades')
  const total = unidadesPorCaja === null ? u : c * unidadesPorCaja + u
  if (total > ENTERO_MAXIMO) {
    throw new CantidadInvalidaError('La cantidad no entra en un entero de 32 bits.')
  }
  return total
}

export interface CajasYUnidades {
  cajas: number
  unidades: number
}

/** Inversa de `aUnidadesBase`; un negativo conserva el signo en cada parte. */
export function desdeUnidadesBase(cantidadBase: number, unidadesPorCaja: number | null): CajasYUnidades {
  if (unidadesPorCaja === null || unidadesPorCaja <= 0) {
    return { cajas: 0, unidades: cantidadBase }
  }
  const magnitud = Math.abs(cantidadBase)
  const signo = cantidadBase < 0 ? -1 : 1
  return {
    cajas: signo * Math.floor(magnitud / unidadesPorCaja),
    unidades: signo * (magnitud % unidadesPorCaja),
  }
}

/**
 * Presentación de referencia del producto. `nombre` es `null` cuando la fuente
 * solo conoce las unidades (un origen sin catálogo).
 */
export interface ReferenciaDePresentacion {
  unidades: number
  nombre: string | null
}

/** Referencia a partir de `unidades_referencia` y `nombre_referencia` de la API; `null` si no hay. */
export function referenciaDeRespuesta(unidades: number | null, nombre: string | null): ReferenciaDePresentacion | null {
  return unidades === null ? null : { unidades, nombre }
}

/** La presentación marcada `es_referencia` del catálogo, con su nombre; `null` si no hay. */
export function referenciaDePresentaciones(
  presentaciones: readonly { nombre: string; unidades_base: number; es_referencia: boolean }[] | undefined,
): ReferenciaDePresentacion | null {
  const referencia = presentaciones?.find((p) => p.es_referencia)
  return referencia === undefined ? null : { unidades: referencia.unidades_base, nombre: referencia.nombre }
}

function unidadesTexto(n: number): string {
  return `${String(n)} ${Math.abs(n) === 1 ? 'unidad' : 'unidades'}`
}

/**
 * Unidades base primero y, entre paréntesis, la equivalencia en la presentación
 * de referencia por su nombre (CAT-08): `"61 unidades (10 Caja x6 + 1 un.)"`,
 * `"60 unidades (10 Caja x6)"`, `"5 unidades"`, `"24 unidades"` (referencia de
 * 1 unidad o sin referencia), `"-13 unidades (-2 Caja x6 - 1 un.)"`.
 */
export function formatearCantidad(cantidadBase: number, referencia: ReferenciaDePresentacion | null): string {
  const base = unidadesTexto(cantidadBase)
  if (referencia === null || referencia.unidades <= 1) return base
  const { cajas, unidades } = desdeUnidadesBase(cantidadBase, referencia.unidades)
  if (cajas === 0) return base
  const nombre = referencia.nombre ?? `Presentación x${String(referencia.unidades)}`
  const resto = unidades === 0 ? '' : ` ${unidades < 0 ? '-' : '+'} ${String(Math.abs(unidades))} un.`
  return `${base} (${String(cajas)} ${nombre}${resto})`
}
