import type { EstadoDeEnvio } from '../../../lib/dispositivo/db'

/**
 * Etiqueta visible del estado de envío de una venta del teléfono (change 22a, `design.md` D13).
 * En el 22a solo existe `PENDIENTE` ("Sin enviar"); los demás los escribe el 22b.
 */
const ETIQUETAS: Record<EstadoDeEnvio, string> = {
  PENDIENTE: 'Sin enviar',
  ACEPTADA: 'Enviada',
  CON_OBSERVACIONES: 'Enviada con observaciones',
  RECHAZADA: 'Rechazada',
}

export function etiquetaDeEnvio(estado: EstadoDeEnvio): string {
  return ETIQUETAS[estado]
}
