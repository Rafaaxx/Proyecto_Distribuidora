import { z } from 'zod'

/**
 * Validación del formulario de ubicación (change 09, tarea 8.2; `design.md` D7,
 * STK-02): UX que evita un viaje al servidor; el servidor y la base siguen siendo
 * la fuente de verdad (`NOMBRE_DUPLICADO`, `VEHICULO_REQUIERE_TOMA`,
 * `UBICACION_CON_STOCK`).
 */
export const TIPOS_DE_UBICACION = ['DEPOSITO', 'VEHICULO', 'OTRO'] as const
export type TipoDeUbicacion = (typeof TIPOS_DE_UBICACION)[number]

export const esquemaUbicacion = z
  .object({
    nombre: z.string().trim().min(1, 'Ingresá el nombre.'),
    tipo: z.enum(TIPOS_DE_UBICACION),
    requiere_toma: z.boolean(),
    activo: z.boolean(),
  })
  .refine((datos) => datos.tipo !== 'VEHICULO' || datos.requiere_toma, {
    message: 'Un vehículo siempre requiere toma.',
    path: ['requiere_toma'],
  })

export type DatosUbicacion = z.infer<typeof esquemaUbicacion>

export function aCuerpoDeUbicacion(datos: DatosUbicacion): DatosUbicacion {
  return { ...datos, nombre: datos.nombre.trim() }
}

const ETIQUETAS_DE_UBICACION: Record<TipoDeUbicacion, string> = {
  DEPOSITO: 'Depósito',
  VEHICULO: 'Vehículo',
  OTRO: 'Otro',
}

export function etiquetaDeTipoDeUbicacion(tipo: string): string {
  return tipo in ETIQUETAS_DE_UBICACION ? ETIQUETAS_DE_UBICACION[tipo as TipoDeUbicacion] : tipo
}

const ETIQUETAS_DE_MOVIMIENTO: Record<string, string> = {
  STOCK_INICIAL: 'Stock inicial',
  COMPRA: 'Compra',
  ANULACION_COMPRA: 'Anulación de compra',
  VENTA: 'Venta',
  ANULACION_VENTA: 'Anulación de venta',
  TRANSFERENCIA_SALIDA: 'Transferencia (salida)',
  TRANSFERENCIA_ENTRADA: 'Transferencia (entrada)',
  AJUSTE: 'Ajuste',
  DIFERENCIA_RENDICION: 'Diferencia de rendición',
}

/** El tipo del catálogo (STK-03) en palabras; uno desconocido se muestra tal cual. */
export function etiquetaDeTipoDeMovimiento(tipo: string): string {
  return ETIQUETAS_DE_MOVIMIENTO[tipo] ?? tipo
}
