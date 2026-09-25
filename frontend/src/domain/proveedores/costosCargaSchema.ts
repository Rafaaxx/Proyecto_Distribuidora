import { z } from 'zod'

/**
 * Validación del formulario de carga de costos (tarea 11.4, spec
 * `administracion-de-proveedores`): UX que evita un viaje al servidor
 * para un error obvio -- el servidor sigue siendo la fuente de verdad
 * (`VALOR_INVALIDO`, `BONIFICACION_INVALIDA`, `PRESENTACION_INVALIDA`).
 * La bonificación se ingresa en porcentaje (`[0, 100)`) y se convierte a
 * fracción recién al construir el comando (`costoBase.ts` la espera como
 * fracción).
 */
const PATRON_DECIMAL = /^\d+(\.\d+)?$/

export const esquemaFilaCosto = z.object({
  productoId: z.uuid('Elegí un producto.'),
  presentacionId: z.uuid('Elegí una presentación.'),
  valor: z
    .string()
    .trim()
    .regex(PATRON_DECIMAL, 'Ingresá un valor mayor a cero.')
    .refine((valor) => Number.parseFloat(valor) > 0, 'Ingresá un valor mayor a cero.'),
  incluyeIva: z.boolean(),
  bonificacionPorcentaje: z
    .string()
    .trim()
    .regex(PATRON_DECIMAL, 'Ingresá un porcentaje entre 0 y 100.')
    .refine((valor) => Number.parseFloat(valor) < 100, 'La bonificación debe ser menor a 100%.'),
  vigenciaDesde: z.string().trim().min(1, 'Elegí una fecha de vigencia.'),
  observacion: z.string(),
})

export type DatosFilaCosto = z.infer<typeof esquemaFilaCosto>

export const esquemaCargaDeCostos = z.object({
  filas: z.array(esquemaFilaCosto).min(1, 'Agregá al menos un costo.'),
})

export type DatosCargaDeCostos = z.infer<typeof esquemaCargaDeCostos>

export const FILA_VACIA: DatosFilaCosto = {
  productoId: '',
  presentacionId: '',
  valor: '',
  incluyeIva: false,
  bonificacionPorcentaje: '0',
  vigenciaDesde: '',
  observacion: '',
}
