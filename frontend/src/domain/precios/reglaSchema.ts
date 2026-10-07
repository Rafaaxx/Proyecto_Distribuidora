import { z } from 'zod'

import { redondearCosto } from '../../lib/money'
import { aImporte, esDecimalNoNegativo, normalizarDecimal, sinCerosFinales } from './decimales'

/**
 * Validación del formulario de regla de margen (change 13, tarea 12.1; PRC-12, PRC-13, D8).
 * La persona escribe un porcentaje (`30` o `12,5`); el comando lleva la fracción de seis
 * decimales como string (TR-02: 30% = `"0.300000"`). Solo UX: el servidor valida igual
 * (`MARGEN_INVALIDO`, `ALCANCE_INVALIDO`, `REGLA_DUPLICADA`).
 */

export const TIPOS_DE_MARGEN = ['MARKUP', 'MARGEN_BRUTO'] as const
export type TipoDeMargen = (typeof TIPOS_DE_MARGEN)[number]

/** De la más específica a la más general (PRC-13). */
export const ALCANCES_CON_ENTIDAD = ['PRODUCTO', 'MARCA', 'CATEGORIA', 'PROVEEDOR'] as const
export const ALCANCES = [...ALCANCES_CON_ENTIDAD, 'LISTA'] as const
export type AlcanceDeRegla = (typeof ALCANCES)[number]

/** Hasta cuatro decimales de porcentaje = seis decimales de fracción. */
const DECIMALES_DE_PORCENTAJE = 4
const CIEN = '100'

/** `"30"` o `"12,5"` (porcentaje) -> `"0.300000"` / `"0.125000"` (fracción de la API). */
export function fraccionDesdePorcentaje(porcentaje: string): string {
  return redondearCosto(aImporte(normalizarDecimal(porcentaje)).div(CIEN)).toFixed(6)
}

/** `"0.300000"` (fracción de la API) -> `"30"`: el porcentaje sin ceros finales. */
export function porcentajeDesdeFraccion(fraccion: string): string {
  return sinCerosFinales(aImporte(fraccion).times(CIEN).toFixed(DECIMALES_DE_PORCENTAJE))
}

export const esquemaRegla = z
  .object({
    tipo: z.enum(TIPOS_DE_MARGEN, { message: 'Elegí el tipo de margen.' }),
    porcentaje: z.string().transform(normalizarDecimal),
    alcance_tipo: z.enum(ALCANCES, { message: 'Elegí el alcance.' }),
    alcance_id: z.string(),
  })
  .superRefine((datos, contexto) => {
    if (!esDecimalNoNegativo(datos.porcentaje, DECIMALES_DE_PORCENTAJE)) {
      contexto.addIssue({
        code: 'custom',
        path: ['porcentaje'],
        message: 'Ingresá un porcentaje de cero o más, con hasta cuatro decimales.',
      })
    } else if (datos.tipo === 'MARGEN_BRUTO' && aImporte(datos.porcentaje).gte(CIEN)) {
      contexto.addIssue({
        code: 'custom',
        path: ['porcentaje'],
        message: 'Un margen bruto debe ser menor que 100%.',
      })
    }
    if (datos.alcance_tipo === 'LISTA' && datos.alcance_id !== '') {
      contexto.addIssue({ code: 'custom', path: ['alcance_id'], message: 'El alcance "Toda la lista" no lleva entidad.' })
    }
    if (datos.alcance_tipo !== 'LISTA' && datos.alcance_id === '') {
      contexto.addIssue({ code: 'custom', path: ['alcance_id'], message: 'Elegí a qué se aplica la regla.' })
    }
  })
export type DatosReglaEntrada = z.input<typeof esquemaRegla>
export type DatosRegla = z.output<typeof esquemaRegla>
