import { z } from 'zod'

import { formatearPorcentaje, parsearImporteDesdeApi } from '../../lib/money'
import { aImporte, esDecimalNoNegativo, normalizarDecimal } from '../precios/decimales'
import { fraccionDesdePorcentaje, porcentajeDesdeFraccion } from '../precios/reglaSchema'

/**
 * Tope de descuento manual de un rol (change 16, tarea 15.4; D13; DSC-06; `01` §19; TR-02, INV-03).
 * La persona escribe el tope como porcentaje (`5`, `12,5`); el comando lleva la fracción de seis
 * decimales como cadena (`"0.050000"`). El 100 % (`"1.000000"`) es "Sin tope". Solo UX: el
 * servidor valida igual (`IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`). Nada pasa por `number`.
 */

/** Hasta cuatro decimales de porcentaje = seis decimales de fracción. */
const DECIMALES_DE_PORCENTAJE = 4

export const esquemaTope = z
  .object({ tope_descuento: z.string().transform(normalizarDecimal) })
  .superRefine((datos, contexto) => {
    const valido =
      esDecimalNoNegativo(datos.tope_descuento, DECIMALES_DE_PORCENTAJE) && aImporte(datos.tope_descuento).lte(100)
    if (!valido) {
      contexto.addIssue({
        code: 'custom',
        path: ['tope_descuento'],
        message: 'Ingresá un porcentaje de 0 a 100, con hasta cuatro decimales.',
      })
    }
  })
  .transform((datos) => ({ tope_descuento: fraccionDesdePorcentaje(datos.tope_descuento) }))

export type DatosTope = z.output<typeof esquemaTope>

/** "Sin tope" en 100 %; en otro caso el porcentaje (`"0.050000"` -> `"5 %"`). */
export function describirTope(fraccion: string): string {
  const tope = parsearImporteDesdeApi(fraccion)
  return tope.eq(1) ? 'Sin tope' : formatearPorcentaje(tope)
}

/** Con tope 0 % todo descuento manual necesita autorización (DSC-06). */
export function esTopeCero(fraccion: string): boolean {
  return parsearImporteDesdeApi(fraccion).isZero()
}

/**
 * El aviso de "tope 0 %" solo corresponde al rol que PUEDE dar descuento manual
 * (`DESCUENTO_MANUAL`) y tiene tope 0: sin el permiso, el tope no cambia nada (DSC-06).
 */
export function avisaTopeCero(rol: { permisos: readonly string[]; tope_descuento: string }): boolean {
  return rol.permisos.includes('DESCUENTO_MANUAL') && esTopeCero(rol.tope_descuento)
}

/** Lo que la persona escribiría para obtener ese tope (`"0.125000"` -> `"12.5"`). */
export function topeEscritoDesdeFraccion(fraccion: string): string {
  return porcentajeDesdeFraccion(fraccion)
}
