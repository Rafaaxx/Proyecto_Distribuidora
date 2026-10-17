import { z } from 'zod'

/**
 * Formulario de un medio de pago (change 17b, `design.md` D2, D3; TR-09). Solo UX: el servidor
 * valida igual (`NOMBRE_INVALIDO`, `NOMBRE_DUPLICADO`, `ULTIMO_MEDIO_ACTIVO`). El nombre se guarda
 * recortado; no se distingue mayúsculas para repetirlo, pero eso lo decide el servidor.
 */
export const esquemaMedioPago = z.object({
  nombre: z.string().trim().min(1, 'Escribí un nombre para el medio de pago.'),
  requiere_referencia: z.boolean(),
})

export type DatosDeMedioPago = z.output<typeof esquemaMedioPago>

const MENSAJES_POR_CODIGO: Record<string, string> = {
  NOMBRE_DUPLICADO: 'Ya hay un medio de pago con ese nombre (aunque esté de baja). Elegí otro, o reactivá el que ya existe.',
  NOMBRE_INVALIDO: 'Escribí un nombre para el medio de pago.',
  ULTIMO_MEDIO_ACTIVO: 'Tiene que quedar al menos un medio de pago activo. Activá otro antes de dar de baja este.',
}

/** El rechazo del servidor en palabras simples; un código desconocido muestra su mensaje. */
export function mensajeDeErrorDeMedioPago(codigo: string | null, mensajeDelServidor: string): string {
  return (codigo !== null ? MENSAJES_POR_CODIGO[codigo] : undefined) ?? mensajeDelServidor
}
