import type { ClaveDeAyuda } from '../../../ayuda/textos'
import type { EstadoDeEnvio } from '../../../lib/dispositivo/db'

/**
 * Etiqueta visible del estado de envío de una venta del teléfono (change 22a, `design.md` D13).
 * `PENDIENTE` es «Sin enviar»; los demás los escribe la sincronización (change 22b, D3, D8).
 */
const ETIQUETAS: Record<EstadoDeEnvio, string> = {
  PENDIENTE: 'Sin enviar',
  ACEPTADA: 'Enviada',
  CON_OBSERVACIONES: 'Con observaciones',
  RECHAZADA: 'Rechazada',
}

export function etiquetaDeEnvio(estado: EstadoDeEnvio): string {
  return ETIQUETAS[estado]
}

/** Ayudas de los estados con problema que aparecen en una lista (sin repetir; «Sin enviar» va aparte). */
export function ayudasDeProblemasEnLista(estados: EstadoDeEnvio[]): ClaveDeAyuda[] {
  const claves = estados
    .filter((e) => e === 'CON_OBSERVACIONES' || e === 'RECHAZADA')
    .map((e) => AYUDA_DE_ENVIO[e])
    .filter((c): c is ClaveDeAyuda => c !== null)
  return [...new Set(claves)]
}

const AYUDA_DE_ENVIO: Record<EstadoDeEnvio, ClaveDeAyuda | null> = {
  PENDIENTE: 'ruta.ventaSinEnviar',
  ACEPTADA: null,
  CON_OBSERVACIONES: 'ruta.ventaConObservaciones',
  RECHAZADA: 'ruta.ventaRechazada',
}

/** Ayuda «(?)» que explica el estado de envío de una venta; la enviada no necesita ninguna (ADR-051). */
export function claveDeAyudaDeEnvio(estado: EstadoDeEnvio): ClaveDeAyuda | null {
  return AYUDA_DE_ENVIO[estado]
}
