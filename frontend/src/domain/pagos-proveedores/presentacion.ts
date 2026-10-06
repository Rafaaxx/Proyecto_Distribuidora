/**
 * Presentación y reglas de pantalla del pago a proveedor ya registrado (change 12, tareas
 * 9.1 y 9.2): etiquetas, si se ofrece "Anular" y el saldo que queda al anular. Lógica pura,
 * sin React; los importes llegan como string de la API y no pasan por `number` (INV-03).
 */

import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { textoDeSaldo } from '../cuentas-corrientes/presentacion'

export const ETIQUETA_DE_ESTADO_DE_PAGO: Record<string, string> = { CONFIRMADA: 'Confirmado', ANULADA: 'Anulado' }

const ETIQUETAS_DE_ORIGEN: Record<string, string> = { COMPRA: 'Compra de contado', INDEPENDIENTE: 'Pago independiente' }

/** Ámbito de los motivos de anulación de un pago (D1). */
export const AMBITO_DE_ANULACION_DE_PAGO = 'ANULACION_PAGO'

export function etiquetaDeOrigen(origen: string): string {
  return ETIQUETAS_DE_ORIGEN[origen] ?? origen
}

export interface PagoAnulable {
  estado: string
  origen: string
  compra_estado: string | null
}

/** El pago de una compra de contado cuya compra sigue `CONFIRMADA` solo se anula con la compra (CMP-05, D2). */
export function esPagoDeCompraVigente(pago: PagoAnulable): boolean {
  return pago.origen === 'COMPRA' && pago.compra_estado === 'CONFIRMADA'
}

/** Si la pantalla ofrece "Anular": el pago está `CONFIRMADA` y no es el de una compra vigente (PAG-03, D2). */
export function puedeAnularse(pago: PagoAnulable): boolean {
  return pago.estado === 'CONFIRMADA' && !esPagoDeCompraVigente(pago)
}

/** Saldo del proveedor tras anular un pago: la anulación aumenta el saldo por el importe del pago (CC-03). */
export function textoDeSaldoTrasAnular(saldoActual: string, importeDelPago: string): string {
  const resultante = redondearImporte(parsearImporteDesdeApi(saldoActual).add(parsearImporteDesdeApi(importeDelPago)))
  return textoDeSaldo('PROVEEDOR', resultante.toFixed(2))
}
