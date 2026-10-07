import { z } from 'zod'

import { aImporte, esDecimalNoNegativo, normalizarDecimal } from './decimales'

/**
 * Precio manual de un producto en el borrador (change 13, tarea 12.1; D7): mayor que cero y
 * con hasta dos decimales; no se redondea con la regla de la lista. Solo UX: el servidor
 * valida igual (`IMPORTE_INVALIDO`, `PRECIO_NO_POSITIVO`).
 */
export const esquemaPrecioManual = z.object({
  precio_final: z
    .string()
    .transform(normalizarDecimal)
    .refine(
      (valor) => esDecimalNoNegativo(valor, 2) && aImporte(valor).gt(0),
      'Ingresá un importe mayor que cero, con hasta dos decimales.',
    ),
})
export type DatosPrecioManualEntrada = z.input<typeof esquemaPrecioManual>
export type DatosPrecioManual = z.output<typeof esquemaPrecioManual>

/** El precio manual ya validado con dos decimales fijos (`"9000.5"` -> `"9000.50"`), tal como viaja. */
export function precioParaApi(precio: string): string {
  return aImporte(normalizarDecimal(precio)).toFixed(2)
}
