/**
 * Auxiliares de texto decimal de las pantallas de precios (change 13, tarea 12.1). Todo
 * se maneja como cadena exacta; los valores se interpretan con decimal.js desde
 * `lib/money.ts` y nunca pasan por `number` (INV-03).
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi } from '../../lib/money'

/** Acepta la coma como separador decimal (es-AR) y la lleva al punto de la API. */
export function normalizarDecimal(texto: string): string {
  return texto.trim().replace(',', '.')
}

/** `valor` es un decimal exacto no negativo con a lo sumo `maxDecimales` decimales. */
export function esDecimalNoNegativo(valor: string, maxDecimales: number): boolean {
  const patron = new RegExp(`^\\d+(\\.\\d{1,${maxDecimales}})?$`)
  return patron.test(valor)
}

/** El decimal ya normalizado como `Importe` (decimal.js). */
export function aImporte(valor: string): Importe {
  return parsearImporteDesdeApi(valor)
}

/** Quita los ceros finales de un decimal con punto (`"12.5000"` -> `"12.5"`, `"30.0000"` -> `"30"`). */
export function sinCerosFinales(valor: string): string {
  if (!valor.includes('.')) return valor
  return valor.replace(/0+$/, '').replace(/\.$/, '')
}
