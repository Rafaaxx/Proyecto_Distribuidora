import { formatearCosto, parsearImporteDesdeApi } from '../../lib/money'

/**
 * Presentación de costos de stock (change 09, tareas 8.3 y 8.4): el costo llega
 * como string de la API y se formatea con `lib/money.ts`, sin pasar nunca por
 * `number` (INV-03). Un costo nulo es "Sin costo" (D10: el producto no tuvo
 * ningún ingreso con costo; no es cero).
 */
export function formatearCostoDeApi(valorApi: string | null | undefined): string {
  if (valorApi === null || valorApi === undefined) return 'Sin costo'
  return `$ ${formatearCosto(parsearImporteDesdeApi(valorApi))}`
}
