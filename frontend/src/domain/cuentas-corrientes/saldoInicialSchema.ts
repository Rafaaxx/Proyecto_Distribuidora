import { z } from 'zod'

import { parsearImporteDesdeApi } from '../../lib/money'

/**
 * Validación del formulario de saldo inicial (change 08, tarea 7.4): UX que
 * evita un viaje al servidor para un error obvio; el servidor sigue siendo la
 * fuente de verdad (`IMPORTE_INVALIDO`, `CUENTA_CON_OPERACIONES`,
 * `CONSUMIDOR_FINAL_SIN_CUENTA`).
 *
 * El importe se conserva como el string que tipeó el usuario (`"150000.00"`):
 * es lo que viaja a la API (`CLAUDE.md` §4, INV-03) y nunca se convierte a
 * `number`. Positivo, a lo sumo dos decimales y dentro de `numeric(14,2)`
 * (doce dígitos enteros).
 */
const MENSAJE_IMPORTE = 'Ingresá un importe mayor a cero, con hasta dos decimales.'
const PATRON_IMPORTE = /^\d{1,12}(\.\d{1,2})?$/

export const esquemaSaldoInicial = z.object({
  importe: z
    .string()
    .trim()
    .regex(PATRON_IMPORTE, MENSAJE_IMPORTE)
        // zod v4 evalúa también el `refine` cuando el patrón falló: sin la guardia,
    // `parsearImporteDesdeApi` lanzaría con un texto que no es un decimal.
    .refine((valor) => !PATRON_IMPORTE.test(valor) || !parsearImporteDesdeApi(valor).isZero(), MENSAJE_IMPORTE),
  sentido: z.enum(['AUMENTA', 'REDUCE']),
})

export type DatosSaldoInicial = z.infer<typeof esquemaSaldoInicial>

/** Un envío que se cortó por la red antes de recibir respuesta. */
export interface EnvioPendiente {
  datos: DatosSaldoInicial
  operationId: string
}

/**
 * Elige el `operation_id` de un envío (INV-06, TR-07): si el usuario reintenta
 * lo mismo que se cortó por la red, se reenvía con el mismo `operation_id` y el
 * servidor no duplica el movimiento; si cambió el importe o el sentido, es otra
 * operación y lleva uno nuevo.
 */
export function resolverOperationId(
  pendiente: EnvioPendiente | null,
  datos: DatosSaldoInicial,
  generar: () => string,
): string {
  if (pendiente && pendiente.datos.importe === datos.importe && pendiente.datos.sentido === datos.sentido) {
    return pendiente.operationId
  }
  return generar()
}
