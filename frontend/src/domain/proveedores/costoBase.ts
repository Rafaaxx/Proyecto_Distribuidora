/**
 * CST-02: costo base por unidad base a partir de lo informado por el
 * proveedor (`design.md` D11, tarea 11.1, **[ALTA: cálculo de costos]**).
 *
 * Función pura, espejo de
 * `backend/app/modules/proveedores/domain/costo_base.py` (mismo cálculo,
 * mismos casos de `shared/fixtures/calculo/cst-02-costo-base.json`).
 *
 * Fórmula (TR-03: sin redondeos intermedios, un único redondeo al final):
 *
 *     costoPorPresentacion = valor * (1 - bonificacion) / (1 + alicuota si incluyeIva sino 1)
 *     costoBase = costoPorPresentacion / unidades
 *
 * El cociente se calcula con la instancia de `lib/money.ts`
 * (`precision: 50`, misma ampliación que `_PRECISION_INTERMEDIA` del
 * backend) para que la única cuantización sea la de `redondearCosto`
 * (`ROUND_HALF_UP`, 6 decimales) al final -- nunca antes.
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearCosto } from '../../lib/money'

/** Valor informado `<= 0` (TR-01). Mismo código que
 * `ValorInvalidoError` del backend (`VALOR_INVALIDO`). */
export class ValorInvalidoError extends Error {
  readonly codigo = 'VALOR_INVALIDO'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'ValorInvalidoError'
  }
}

/** Bonificación fuera de `[0, 1)` (TR-02). Mismo código que
 * `BonificacionInvalidaError` del backend (`BONIFICACION_INVALIDA`). */
export class BonificacionInvalidaError extends Error {
  readonly codigo = 'BONIFICACION_INVALIDA'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'BonificacionInvalidaError'
  }
}

/**
 * Calcula el costo base por unidad base de una presentación informada
 * (CST-02).
 *
 * - `valor`: lo pagado por la presentación completa, cadena decimal exacta,
 *   `> 0` (`ValorInvalidoError` si no).
 * - `incluyeIva`: si `valor` ya incluye el IVA de `alicuota`.
 * - `alicuota`: la alícuota de IVA del producto (fracción, cadena decimal
 *   exacta, `>= 0`).
 * - `bonificacion`: fracción en `[0, 1)`, cadena decimal exacta
 *   (`BonificacionInvalidaError` si no).
 * - `unidades`: unidades base de la presentación informada, entero seguro
 *   `>= 1` (una presentación ya validada por `catalogo`, CAT-02/INV-04 --
 *   acá es un invariante del llamador, no una entrada de usuario, así que
 *   se afirma con `Error` liso en vez de un error de dominio con código
 *   propio).
 */
export function calcularCostoBase(
  valor: string,
  incluyeIva: boolean,
  alicuota: string,
  bonificacion: string,
  unidades: number,
): Importe {
  const valorDecimal = parsearImporteDesdeApi(valor)
  const alicuotaDecimal = parsearImporteDesdeApi(alicuota)
  const bonificacionDecimal = parsearImporteDesdeApi(bonificacion)

  if (valorDecimal.lte(0)) {
    throw new ValorInvalidoError('El valor informado debe ser mayor a cero.')
  }
  if (bonificacionDecimal.lt(0) || bonificacionDecimal.gte(1)) {
    throw new BonificacionInvalidaError(
      'La bonificación debe estar entre 0 (inclusive) y 1 (exclusive).',
    )
  }
  if (!Number.isSafeInteger(unidades) || unidades < 1) {
    throw new Error(
      `Las unidades de la presentación deben ser un entero mayor o igual a 1 (recibido ${String(unidades)}).`,
    )
  }

  const uno = parsearImporteDesdeApi('1')
  let costoPorPresentacion = valorDecimal.mul(uno.sub(bonificacionDecimal))
  if (incluyeIva) {
    costoPorPresentacion = costoPorPresentacion.div(uno.add(alicuotaDecimal))
  }
  const costoSinRedondear = costoPorPresentacion.div(unidades)

  return redondearCosto(costoSinRedondear)
}
