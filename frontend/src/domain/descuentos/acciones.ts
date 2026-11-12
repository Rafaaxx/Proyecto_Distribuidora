/**
 * Acciones de una regla de descuento (DSC-04, DSC-07, TR-03; `design.md` D10 del change 16).
 * Espejo de `backend/app/modules/descuentos/domain/acciones.py`.
 *
 * Todo redondeo pasa por `lib/money.ts` (`ROUND_HALF_UP`); nada se convierte a `number`.
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'

/**
 * Descuento de `porcentaje` (fracción, cadena exacta) sobre el importe de cada línea, redondeado
 * línea por línea a 2 decimales con mitad hacia arriba (DSC-07). Nunca se calcula sobre el total.
 */
export function descuentoPorcentual(importes: readonly Importe[], porcentaje: string): Importe[] {
  const fraccion = parsearImporteDesdeApi(porcentaje)
  return importes.map((importe) => redondearImporte(importe.times(fraccion)))
}

/**
 * Reparte `importeFijo` entre las líneas en proporción a su importe, cada parte redondeada a 2
 * decimales. El remanente de redondeo, positivo o negativo, va a la línea de mayor importe (la
 * primera si empatan). Si el importe supera la suma de las líneas se aplica esa suma: ninguna
 * línea queda con neto negativo (DSC-04, D10). Las partes suman exactamente lo aplicado.
 */
export function repartirImporteFijo(importes: readonly Importe[], importeFijo: string): Importe[] {
  const fijo = parsearImporteDesdeApi(importeFijo)
  const cero = redondearImporte('0')
  const total = importes.reduce((suma, importe) => suma.plus(importe), cero)
  const aplicado = redondearImporte(fijo.lessThan(total) ? fijo : total)
  if (aplicado.lessThanOrEqualTo(0) || total.lessThanOrEqualTo(0)) {
    return importes.map(() => cero)
  }

  const partes = importes.map((importe) => redondearImporte(aplicado.times(importe).div(total)))
  const remanente = aplicado.minus(partes.reduce((suma, parte) => suma.plus(parte), cero))
  if (!remanente.isZero()) {
    // Mayor importe; en empate, la primera del orden de la venta.
    let mayor = 0
    importes.forEach((importe, posicion) => {
      if (importe.greaterThan(importes[mayor] as Importe)) {
        mayor = posicion
      }
    })
    partes[mayor] = (partes[mayor] as Importe).plus(remanente)
  }
  return partes
}
