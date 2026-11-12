/**
 * Condición de volumen de una regla de descuento (DSC-02, DSC-03; `design.md` D5, D6 del change
 * 16). Espejo de `backend/app/modules/descuentos/domain/condicion.py`.
 *
 * La medida se calcula con aritmética racional exacta sobre `bigint` (cociente de enteros, sin
 * redondear) y se compara contra el umbral también exacto: tres líneas de un tercio de caja suman
 * exactamente 1, no 0,9999. Nada se convierte a `number` para calcular (INV-03).
 */

import { parsearImporteDesdeApi } from '../../lib/money'
import type { AlcanceRegla, LineaVenta, Medida, ReglaDescuento } from './tipos'

/** Fracción `num / den` con `den > 0`, siempre reducida. */
export interface Racional {
  readonly num: bigint
  readonly den: bigint
}

function mcd(a: bigint, b: bigint): bigint {
  let x = a < 0n ? -a : a
  let y = b < 0n ? -b : b
  while (y !== 0n) {
    ;[x, y] = [y, x % y]
  }
  return x
}

export function racional(num: bigint, den: bigint): Racional {
  if (den === 0n) {
    throw new RangeError('El denominador de un racional no puede ser cero')
  }
  const signo = den < 0n ? -1n : 1n
  const divisor = mcd(num, den) || 1n
  return { num: (signo * num) / divisor, den: (signo * den) / divisor }
}

/** Racional exacto de una cadena decimal (`"31250.00"` -> 3125000/100), sin pasar por `number`. */
export function racionalDeDecimal(valor: string): Racional {
  const exacto = parsearImporteDesdeApi(valor).toFixed()
  const [entero = '0', decimales = ''] = exacto.split('.')
  return racional(BigInt(entero + decimales), 10n ** BigInt(decimales.length))
}

function sumar(a: Racional, b: Racional): Racional {
  return racional(a.num * b.den + b.num * a.den, a.den * b.den)
}

/** `-1`, `0` o `1` según `a` sea menor, igual o mayor que `b`. */
export function compararRacionales(a: Racional, b: Racional): -1 | 0 | 1 {
  const izquierda = a.num * b.den
  const derecha = b.num * a.den
  return izquierda < derecha ? -1 : izquierda > derecha ? 1 : 0
}

function esElegible(alcances: readonly AlcanceRegla[], linea: LineaVenta): boolean {
  return alcances.some(
    (alcance) =>
      (alcance.tipo === 'PRODUCTO' && alcance.entidadId === linea.productoId) ||
      (alcance.tipo === 'CATEGORIA' && alcance.entidadId === linea.categoriaId) ||
      (alcance.tipo === 'MARCA' && alcance.entidadId === linea.marcaId),
  )
}

/**
 * Posiciones, en el orden de la venta, de las líneas elegibles: todas para una regla de
 * operación; para una de alcance, las que coinciden con alguno de sus alcances por producto,
 * categoría o marca (unión, D6).
 */
export function indicesElegibles(regla: ReglaDescuento, lineas: readonly LineaVenta[]): number[] {
  const posiciones = lineas.map((_, posicion) => posicion)
  if (regla.tipo === 'VOLUMEN_OPERACION') {
    return posiciones
  }
  return posiciones.filter((posicion) => esElegible(regla.alcances, lineas[posicion] as LineaVenta))
}

export function lineasElegibles(regla: ReglaDescuento, lineas: readonly LineaVenta[]): LineaVenta[] {
  return indicesElegibles(regla, lineas).map((posicion) => lineas[posicion] as LineaVenta)
}

/** Suma exacta de la medida sobre `lineas`. */
export function medir(medida: Medida, lineas: readonly LineaVenta[]): Racional {
  let total = racional(0n, 1n)
  for (const linea of lineas) {
    if (medida === 'UNIDADES_BASE') {
      total = sumar(total, racional(BigInt(linea.cantidadBase), 1n))
    } else if (medida === 'IMPORTE_BRUTO') {
      total = sumar(total, racionalDeDecimal(linea.bruto))
    } else {
      total = sumar(total, racional(BigInt(linea.cantidadBase), BigInt(linea.unidadesReferencia)))
    }
  }
  return total
}

/**
 * `true` si la medida de las líneas elegibles cumple el operador contra el umbral. Una regla sin
 * líneas elegibles no aplica.
 */
export function cumpleCondicion(regla: ReglaDescuento, lineas: readonly LineaVenta[]): boolean {
  const elegibles = lineasElegibles(regla, lineas)
  if (elegibles.length === 0) {
    return false
  }
  const comparacion = compararRacionales(medir(regla.medida, elegibles), racionalDeDecimal(regla.umbral))
  return regla.operador === 'GTE' ? comparacion >= 0 : comparacion > 0
}
