/**
 * Presentación de la venta ya registrada y de sus lecturas (change 18a, tareas 12.2 y 12.3;
 * spec `administracion-de-ventas`; `design.md` D6, D21; SYN-07, STK-05). Lógica pura, sin React;
 * los importes llegan como string de la API y no pasan por `number` (INV-03).
 */

import { formatearMonto } from '../cuentas-corrientes/presentacion'
import { formatearCantidad } from '../stock/cantidades'

export const ETIQUETA_DE_ESTADO_DE_VENTA: Record<string, string> = { CONFIRMADA: 'Confirmada', ANULADA: 'Anulada' }

const ETIQUETAS_DE_FACTURACION: Record<string, string> = {
  NO_REQUIERE: 'No requiere factura',
  PENDIENTE: 'Pendiente de facturar',
  PARCIAL: 'Facturada en parte',
  FACTURADA: 'Facturada',
}

const ETIQUETAS_DE_MODO: Record<string, string> = { ONLINE: 'Con conexión', OFFLINE: 'Sin conexión' }

const ETIQUETAS_DE_VERSION: Record<string, string> = {
  VIGENTE: 'vigente',
  HISTORICA: 'anterior',
  PROGRAMADA: 'programada',
}

/** Ámbito de los motivos para vender con otra lista o con una versión anterior (PRC-21, D6). */
export const AMBITO_DE_LISTA_ANTERIOR = 'LISTA_ANTERIOR'

export function etiquetaDeEstadoDeVenta(estado: string): string {
  return ETIQUETA_DE_ESTADO_DE_VENTA[estado] ?? estado
}

export function etiquetaDeEstadoDeFacturacion(estado: string): string {
  return ETIQUETAS_DE_FACTURACION[estado] ?? estado
}

export function etiquetaDeModoDeConfirmacion(modo: string): string {
  return ETIQUETAS_DE_MODO[modo] ?? modo
}

/** `"Versión 2 (vigente)"`, `"Versión 1 (anterior)"`. */
export function etiquetaDeVersion(numero: number, estado: string): string {
  return `Versión ${String(numero)} (${ETIQUETAS_DE_VERSION[estado] ?? estado.toLowerCase()})`
}

export interface CantidadDeLinea {
  cantidad: number
  presentacion_nombre: string | null
  cantidad_base: number
}

/** La cantidad en su presentación y, entre paréntesis, la equivalencia en unidades (CAT-08). */
export function textoDeCantidadDeLinea(linea: CantidadDeLinea): string {
  const presentacion = linea.presentacion_nombre ?? 'Presentación'
  return `${String(linea.cantidad)} × ${presentacion} (${formatearCantidad(linea.cantidad_base, null)})`
}

// --- Observaciones de sincronización (SYN-07) --------------------------------------------

export interface ObservacionDeVenta {
  codigo: string
  estado: string
  detalle: { [clave: string]: unknown } | null
}

const ETIQUETAS_DE_OBSERVACION: Record<string, string> = {
  STOCK_NEGATIVO: 'Stock negativo',
  VENTA_SIN_COSTO: 'Venta sin costo',
  JORNADA_LIBERADA: 'Jornada liberada',
  LISTA_NO_VIGENTE: 'Lista no vigente',
  PERMISO_REVOCADO: 'Permiso revocado',
  CLIENTE_NO_HABILITADO: 'Cliente no habilitado',
  CONSUMIDOR_FINAL_CON_DEUDA: 'Consumidor final con deuda',
  MEDIO_INACTIVO: 'Medio de pago inactivo',
  REFERENCIA_FALTANTE: 'Falta la referencia',
}

export function etiquetaDeObservacionDeVenta(codigo: string): string {
  return ETIQUETAS_DE_OBSERVACION[codigo] ?? codigo
}

function lineaDe(observacion: ObservacionDeVenta): string | null {
  const id = observacion.detalle?.linea_id
  return typeof id === 'string' && id !== '' ? id : null
}

/** Las observaciones que apuntan a la línea `lineaId` (el detalle trae su `linea_id`). */
export function observacionesDeLineaDeVenta(
  observaciones: readonly ObservacionDeVenta[],
  lineaId: string,
): ObservacionDeVenta[] {
  return observaciones.filter((observacion) => lineaDe(observacion) === lineaId)
}

/** Las que no son de una línea (o no dicen cuál): nunca se esconden. */
export function observacionesGeneralesDeVenta(observaciones: readonly ObservacionDeVenta[]): ObservacionDeVenta[] {
  return observaciones.filter((observacion) => lineaDe(observacion) === null)
}

function textoONulo(valor: unknown): string | null {
  return typeof valor === 'string' ? valor : null
}

/** Texto de apoyo: el saldo resultante del stock negativo, o el total y lo cobrado del consumidor final. */
export function detalleDeObservacionDeVenta(observacion: ObservacionDeVenta): string | null {
  const detalle = observacion.detalle
  if (detalle === null) return null
  if (observacion.codigo === 'STOCK_NEGATIVO' && typeof detalle.saldo_resultante === 'number') {
    return `Saldo resultante: ${formatearCantidad(detalle.saldo_resultante, null)}`
  }
  if (observacion.codigo === 'CONSUMIDOR_FINAL_CON_DEUDA') {
    const total = textoONulo(detalle.total)
    const cobranza = textoONulo(detalle.cobranza)
    if (total !== null && cobranza !== null) return `Total ${formatearMonto(total)} · cobrado ${formatearMonto(cobranza)}`
  }
  return null
}
