/**
 * Presentación y reglas de pantalla de la cobranza ya registrada (change 17, tarea 14.1;
 * `design.md` D7, D13, D19). Lógica pura, sin React; los importes llegan como string de la API y
 * no pasan por `number` (INV-03).
 */

import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { formatearMonto, textoDeSaldo } from '../cuentas-corrientes/presentacion'
import {
  detalleDeObservacion as detalleDeObservacionDeRevision,
  etiquetaDeObservacion as etiquetaDeObservacionDeRevision,
} from '../revision/detalleDeObservacion'

export const ETIQUETA_DE_ESTADO_DE_COBRANZA: Record<string, string> = { CONFIRMADA: 'Confirmada', ANULADA: 'Anulada' }

const ETIQUETAS_DE_ORIGEN: Record<string, string> = { INDEPENDIENTE: 'Cobranza independiente', VENTA: 'Cobro de una venta' }

/** Ámbito de los motivos de anulación de una cobranza (D6). */
export const AMBITO_DE_ANULACION_DE_COBRANZA = 'ANULACION_COBRANZA'

export function etiquetaDeOrigenDeCobranza(origen: string): string {
  return ETIQUETAS_DE_ORIGEN[origen] ?? origen
}

export interface CobranzaAnulable {
  estado: string
  origen: string
}

/** Si la pantalla ofrece "Anular": `CONFIRMADA` y de origen `INDEPENDIENTE` (COB-05, D7). */
export function puedeAnularse(cobranza: CobranzaAnulable): boolean {
  return cobranza.estado === 'CONFIRMADA' && cobranza.origen === 'INDEPENDIENTE'
}

/** Saldo del cliente tras anular: la anulación devuelve el importe a la deuda (CC-02). */
export function textoDeSaldoTrasAnular(saldoActual: string, importeDeLaCobranza: string): string {
  const resultante = redondearImporte(
    parsearImporteDesdeApi(saldoActual).add(parsearImporteDesdeApi(importeDeLaCobranza)),
  )
  return textoDeSaldo('CLIENTE', resultante.toFixed(2))
}

// --- Observaciones de sincronización (SYN-07) --------------------------------------------

export interface ObservacionDeCobranza {
  codigo: string
  estado: string
  detalle: { [clave: string]: unknown } | null
  // Change 25 (D11, SYN-08): la resolución, solo lectura.
  resuelto_por_nombre?: string | null
  resuelto_en?: string | null
  comentario?: string | null
}

const CODIGOS_DE_LINEA: readonly string[] = ['MEDIO_INACTIVO', 'REFERENCIA_FALTANTE']

const MOTIVOS_DE_PERMISO_REVOCADO: Record<string, string> = {
  PERMISO_QUITADO: 'Se le quitó el permiso de cobrar',
  USUARIO_INACTIVO: 'El usuario estaba dado de baja',
  ROL_INACTIVO: 'El rol estaba dado de baja',
}

/** La etiqueta es la de la bandeja de revisión (change 25, D12): una sola lista de títulos. */
export function etiquetaDeObservacion(codigo: string): string {
  return etiquetaDeObservacionDeRevision(codigo)
}

/** Posición (desde 0) de la línea que causó una observación de medio, o `null` si no la trae. */
function lineaDe(observacion: ObservacionDeCobranza): number | null {
  if (!CODIGOS_DE_LINEA.includes(observacion.codigo)) return null
  const linea = observacion.detalle?.medio
  return typeof linea === 'number' && Number.isInteger(linea) && linea >= 0 ? linea : null
}

/** Las observaciones de medio que apuntan a la línea `indice`, en el orden en que llegaron. */
export function observacionesDeLinea(
  observaciones: readonly ObservacionDeCobranza[],
  indice: number,
): ObservacionDeCobranza[] {
  return observaciones.filter((observacion) => lineaDe(observacion) === indice)
}

/** Las que no son de una línea (o no dicen cuál): nunca se esconden. */
export function observacionesGenerales(observaciones: readonly ObservacionDeCobranza[]): ObservacionDeCobranza[] {
  return observaciones.filter((observacion) => lineaDe(observacion) === null)
}

/** Texto de apoyo de una observación: medio e importe de la línea, o el motivo del permiso. */
export function detalleDeObservacion(observacion: ObservacionDeCobranza): string | null {
  const detalle = observacion.detalle
  if (detalle === null) return null
  if (CODIGOS_DE_LINEA.includes(observacion.codigo)) {
    const { nombre, importe } = detalle
    if (typeof nombre === 'string' && typeof importe === 'string') return `${nombre} · ${formatearMonto(importe)}`
    return null
  }
  if (observacion.codigo === 'PERMISO_REVOCADO' && typeof detalle.motivo === 'string') {
    return MOTIVOS_DE_PERMISO_REVOCADO[detalle.motivo] ?? null
  }
  // Change 25 (D12): los demás códigos (p. ej. `JORNADA_RENDIDA`) con su detalle legible.
  const lineas = detalleDeObservacionDeRevision(observacion.codigo, detalle)
  return lineas.length === 0 ? null : lineas.join(' · ')
}
