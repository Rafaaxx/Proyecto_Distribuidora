import { z } from 'zod'

import type { FiltrosEstadoDeCuenta } from '../../features/cuentas-corrientes/claves'

/**
 * Filtro de período del estado de cuenta (change 08, tarea 7.3, `design.md`
 * D9): fechas de negocio `aaaa-mm-dd` (TR-04), ambas opcionales e inclusivas.
 * Validación de UX: el servidor sigue siendo la fuente de verdad
 * (`RANGO_DE_FECHAS_INVALIDO`). Las fechas `aaaa-mm-dd` se ordenan igual como
 * texto que como fecha, así que no hace falta construir ningún `Date`.
 */
export const esquemaPeriodo = z
  .object({
    desde: z.string(),
    hasta: z.string(),
  })
  .refine((periodo) => periodo.desde === '' || periodo.hasta === '' || periodo.desde <= periodo.hasta, {
    message: '"Desde" no puede ser posterior a "Hasta".',
    path: ['hasta'],
  })

export type DatosPeriodo = z.infer<typeof esquemaPeriodo>

/** Los campos vacíos del formulario no viajan como filtro. */
export function aFiltros(periodo: DatosPeriodo): FiltrosEstadoDeCuenta {
  return {
    ...(periodo.desde !== '' && { desde: periodo.desde }),
    ...(periodo.hasta !== '' && { hasta: periodo.hasta }),
  }
}
