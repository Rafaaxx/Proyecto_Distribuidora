import { z } from 'zod'

import { aImporte, esDecimalNoNegativo, normalizarDecimal } from './decimales'

/**
 * Validación de los formularios de lista y de redondeo por categoría (change 13, tarea 12.1;
 * PRC-01, PRC-14, D9). Solo UX: el servidor valida igual (`REDONDEO_INVALIDO`,
 * `NOMBRE_INVALIDO`, `NOMBRE_DUPLICADO`). El múltiplo viaja como string (INV-03).
 */

/** Catálogo cerrado de `precios/domain/redondeo.py` (PRC-14). */
export const DIRECCIONES_REDONDEO = ['ARRIBA', 'CERCANO', 'ABAJO'] as const
export type DireccionRedondeo = (typeof DIRECCIONES_REDONDEO)[number]

export const ETIQUETA_DE_DIRECCION: Record<DireccionRedondeo, string> = {
  ARRIBA: 'Hacia arriba',
  CERCANO: 'Al más cercano',
  ABAJO: 'Hacia abajo',
}

/** Múltiplo de redondeo: mayor que cero, con hasta dos decimales (D9). */
const multiplo = z
  .string()
  .transform(normalizarDecimal)
  .refine(
    (valor) => esDecimalNoNegativo(valor, 2) && aImporte(valor).gt(0),
    'Ingresá un múltiplo mayor que cero, con hasta dos decimales.',
  )

export const esquemaLista = z.object({
  nombre: z.string().trim().min(1, 'Ingresá un nombre.'),
  redondeo_multiplo: multiplo,
  redondeo_direccion: z.enum(DIRECCIONES_REDONDEO, { message: 'Elegí una dirección de redondeo.' }),
})
/** La edición suma la actividad (`LISTA_EN_USO` impide desactivar la predeterminada o una asignada). */
export const esquemaListaEdicion = esquemaLista.extend({ activo: z.boolean() })
export type DatosListaEdicionEntrada = z.input<typeof esquemaListaEdicion>
export type DatosListaEdicion = z.output<typeof esquemaListaEdicion>
export type DatosListaEntrada = z.input<typeof esquemaLista>
export type DatosLista = z.output<typeof esquemaLista>

export const esquemaRedondeoCategoria = z.object({
  categoria_id: z.string().min(1, 'Elegí una categoría.'),
  multiplo,
  direccion: z.enum(DIRECCIONES_REDONDEO, { message: 'Elegí una dirección de redondeo.' }),
})
export type DatosRedondeoCategoriaEntrada = z.input<typeof esquemaRedondeoCategoria>
export type DatosRedondeoCategoria = z.output<typeof esquemaRedondeoCategoria>
