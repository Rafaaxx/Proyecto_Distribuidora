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

/** `"5 cajas + 1 un."`, `"2 cajas"`, `"4 un."`. */
export function formatearCantidad(cantidadBase: number, unidadesPorCaja: number | null): string {
  const { cajas, unidades } = desdeUnidadesBase(cantidadBase, unidadesPorCaja)
  const partes: string[] = []
  if (cajas !== 0) partes.push(`${String(cajas)} ${Math.abs(cajas) === 1 ? 'caja' : 'cajas'}`)
  if (unidades !== 0) partes.push(`${String(unidades)} un.`)
  return partes.length === 0 ? '0 un.' : partes.join(' + ')
}
