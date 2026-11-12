import type { ClaveDeAyuda } from '../../../ayuda/textos'
import type { AnulacionLocal, EstadoDeEnvio } from '../../../lib/dispositivo/db'

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

/** Etiqueta de una venta con anulación en el teléfono (change 22d, D10). */
export const ETIQUETA_ANULADA = 'Anulada'

/**
 * Una venta se ve «Anulada» mientras su anulación no haya sido rechazada: rechazada, la venta
 * sigue vigente (D7, SYN-06). Sin enviar, aceptada o con observaciones cuenta como anulada.
 */
export function estaAnulada(anulacion: Pick<AnulacionLocal, 'estado_envio'> | null | undefined): boolean {
  return anulacion !== null && anulacion !== undefined && anulacion.estado_envio !== 'RECHAZADA'
}

/** Ayuda «(?)» del estado de envío de una anulación; la rechazada tiene la suya (D12). */
export function claveDeAyudaDeEnvioDeAnulacion(estado: EstadoDeEnvio): ClaveDeAyuda | null {
  return estado === 'RECHAZADA' ? 'ruta.anulacionRechazada' : AYUDA_DE_ENVIO[estado]
}

/**
 * Ayuda «(?)» del estado de envío de una cobranza (change 23, D12): solo la rechazada tiene la suya;
 * el resto se explica en «Observaciones y rechazos».
 */
export function claveDeAyudaDeEnvioDeCobranza(estado: EstadoDeEnvio): ClaveDeAyuda | null {
  return estado === 'RECHAZADA' ? 'ruta.cobranzaRechazada' : null
}

/** Ayudas de una lista de cobranzas: la de la rechazada, una sola vez. */
export function ayudasDeProblemasEnListaDeCobranzas(estados: EstadoDeEnvio[]): ClaveDeAyuda[] {
  return estados.includes('RECHAZADA') ? ['ruta.cobranzaRechazada'] : []
}
