import { z } from 'zod'

/**
 * Formulario de los datos de la organización (change 20, D15; VTA-13). Solo UX: el servidor valida
 * igual (`NOMBRE_DE_ORGANIZACION_INVALIDO`, `CUIT_INVALIDO`) y normaliza el CUIT a 11 dígitos.
 * El nombre se recorta y no puede quedar vacío; el CUIT es opcional.
 */
export const NOMBRE_DE_ORGANIZACION_MAXIMO = 200

export const esquemaDatosOrganizacion = z.object({
  nombre: z
    .string()
    .trim()
    .min(1, 'Escribí el nombre de la organización.')
    .max(NOMBRE_DE_ORGANIZACION_MAXIMO, `El nombre no puede superar los ${NOMBRE_DE_ORGANIZACION_MAXIMO} caracteres.`),
  cuit: z.string(),
})

export type DatosDeOrganizacion = z.output<typeof esquemaDatosOrganizacion>
