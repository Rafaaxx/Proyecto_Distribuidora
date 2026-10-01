/**
 * CST-11 y CST-12: costo promedio ponderado móvil (`01` §6.2, `design.md` D4,
 * D6, D10, D14, **[ALTA: cálculo de costos]**).
 *
 * Funciones puras, espejo de
 * `backend/app/modules/costeo/domain/costo_promedio.py` (mismo cálculo, mismos
 * casos de `shared/fixtures/calculo/cst-11-costo-promedio.json`). Sirven para
 * PREVISUALIZAR el promedio resultante en la pantalla de stock inicial a quien
 * tiene `VER_COSTOS`; el servidor recalcula siempre (TR-10).
 *
 * Fórmula de un ingreso con costo (CST-11):
 *
 *     stock previo > 0:   (stock * promedio + cantidad * costo) / (stock + cantidad)
 *     stock previo <= 0:  costo del ingreso
 *
 * El cociente se calcula con la instancia de `lib/money.ts` (`precision: 50`,
 * misma ampliación que `_PRECISION_INTERMEDIA` del backend) para que la única
 * cuantización sea la de `redondearCosto` (`ROUND_HALF_UP`, 6 decimales) al
 * final -- nunca antes (TR-02, TR-03). Un egreso no cambia el promedio y se
 * valoriza a ese promedio (CST-12).
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearCosto } from '../../lib/money'

/** Mayor valor de `numeric(18,6)`: 12 dígitos enteros y 6 decimales. */
export const COSTO_MAXIMO = '999999999999.999999'

/** Rango de `integer` de PostgreSQL (INV-04). */
export const STOCK_MAXIMO = 2_147_483_647
export const STOCK_MINIMO = -2_147_483_648

const FORMATO_COSTO = /^[0-9]+(\.[0-9]{1,6})?$/

/** Costo que no es un decimal positivo con hasta 6 decimales o que no entra en
 * `numeric(18,6)` (D6). Mismo código que `CostoInvalidoError` del backend. */
export class CostoInvalidoError extends Error {
  readonly codigo = 'COSTO_INVALIDO'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'CostoInvalidoError'
  }
}

/** Cantidad que no es un entero positivo (INV-04). Mismo código que el backend. */
export class CantidadInvalidaError extends Error {
  readonly codigo = 'CANTIDAD_INVALIDA'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'CantidadInvalidaError'
  }
}

/** Stock positivo sin costo promedio (D10). Mismo código que el backend. */
export class PromedioInconsistenteError extends Error {
  readonly codigo = 'PROMEDIO_INCONSISTENTE'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'PromedioInconsistenteError'
  }
}

/** Stock total fuera de un entero de 32 bits (INV-04). Mismo código que el backend. */
export class StockFueraDeRangoError extends Error {
  readonly codigo = 'STOCK_FUERA_DE_RANGO'

  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'StockFueraDeRangoError'
  }
}

export interface ResultadoDeIngreso {
  promedioNuevo: Importe
  stockNuevo: number
}

export interface ResultadoDeEgreso {
  promedioNuevo: Importe | null
  costoValorizacion: Importe | null
  stockNuevo: number
}

/**
 * Devuelve el costo por unidad base como valor exacto o lanza
 * `CostoInvalidoError` (D6-A): cadena decimal positiva con hasta 6 decimales,
 * dentro de `numeric(18,6)`. NO redondea: más decimales se rechazan (TR-02). Un
 * `number` nativo se rechaza (INV-03).
 */
export function validarCosto(valor: string): Importe {
  if (typeof valor !== 'string' || !FORMATO_COSTO.test(valor)) {
    throw new CostoInvalidoError(
      `El costo ${JSON.stringify(valor)} no es un decimal positivo con hasta seis decimales.`,
    )
  }
  const decimal = parsearImporteDesdeApi(valor)
  if (decimal.lte(0)) {
    throw new CostoInvalidoError(`El costo ${valor} tiene que ser mayor que cero.`)
  }
  if (decimal.gt(parsearImporteDesdeApi(COSTO_MAXIMO))) {
    throw new CostoInvalidoError(`El costo ${valor} supera el máximo de ${COSTO_MAXIMO}.`)
  }
  return redondearCosto(decimal)
}

function validarCantidad(cantidad: number): number {
  if (!Number.isSafeInteger(cantidad)) {
    throw new CantidadInvalidaError(`La cantidad ${String(cantidad)} tiene que ser un entero.`)
  }
  if (cantidad <= 0) {
    throw new CantidadInvalidaError(`La cantidad ${String(cantidad)} tiene que ser mayor que cero.`)
  }
  return cantidad
}

function validarStock(stock: number): number {
  if (stock < STOCK_MINIMO || stock > STOCK_MAXIMO) {
    throw new StockFueraDeRangoError(
      `El stock total ${String(stock)} no entra en un entero de 32 bits.`,
    )
  }
  return stock
}

/**
 * CST-11: recalcula el promedio por un ingreso con costo.
 *
 * - `stockPrevio`: stock total del producto en la organización antes del
 *   ingreso; puede ser cero o negativo.
 * - `promedioPrevio`: promedio vigente (cadena decimal), `null` si el producto
 *   nunca tuvo un ingreso con costo (D10).
 * - `cantidad`: unidades base que ingresan, entero `> 0`.
 * - `costoIngreso`: costo por unidad base (`CostoInvalidoError` si no cumple D6).
 */
export function calcularIngreso(
  stockPrevio: number,
  promedioPrevio: string | null,
  cantidad: number,
  costoIngreso: string,
): ResultadoDeIngreso {
  const costo = validarCosto(costoIngreso)
  const cantidadValidada = validarCantidad(cantidad)
  const stockNuevo = validarStock(stockPrevio + cantidadValidada)

  if (stockPrevio <= 0) {
    return { promedioNuevo: costo, stockNuevo }
  }

  if (promedioPrevio === null) {
    throw new PromedioInconsistenteError(
      `El producto tiene ${String(stockPrevio)} unidades y ningún costo promedio.`,
    )
  }

  const promedio = parsearImporteDesdeApi(promedioPrevio)
  const ponderado = promedio
    .mul(stockPrevio)
    .add(costo.mul(cantidadValidada))
    .div(stockNuevo)

  return { promedioNuevo: redondearCosto(ponderado), stockNuevo }
}

/**
 * CST-12: un egreso no modifica el promedio y se valoriza al promedio vigente.
 * `cantidad` es la magnitud (`> 0`); el stock resultante puede ser negativo: la
 * condición de saldo suficiente es de `stock` (STK-05).
 */
export function calcularEgreso(
  stockPrevio: number,
  promedioPrevio: string | null,
  cantidad: number,
): ResultadoDeEgreso {
  const cantidadValidada = validarCantidad(cantidad)
  const stockNuevo = validarStock(stockPrevio - cantidadValidada)
  const promedio = promedioPrevio === null ? null : parsearImporteDesdeApi(promedioPrevio)

  return { promedioNuevo: promedio, costoValorizacion: promedio, stockNuevo }
}
