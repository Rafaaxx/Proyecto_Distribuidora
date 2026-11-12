import type { Mock } from 'vitest'

import { enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'
import { EFECTIVO_ID, MEDIOS_DE_PAGO, MOTIVO_ID, PROVEEDOR_ID, TRANSFERENCIA_ID } from '../compras/comprasDePrueba'

export { EFECTIVO_ID, MOTIVO_ID, PROVEEDOR_ID, TRANSFERENCIA_ID }

/**
 * Datos y reglas de API compartidos por las pruebas de las pantallas de pagos a proveedores
 * (change 12, grupo 9). `Bodega Sur` debe $153.720,00; `Bodega Norte` está de baja.
 */

export const PAGO_ID = '55555555-5555-4555-8555-555555555555'
export const PAGO_DE_COMPRA_ID = '66666666-6666-4666-8666-666666666666'
export const COMPRA_DEL_PAGO_ID = '99999999-9999-4999-8999-999999999999'
export const PROVEEDOR_NORTE_ID = '12121212-1212-4121-8121-121212121212'
export const MOTIVO_PAGO_ID = 'abababab-abab-4bab-8bab-abababababab'
export const OTRO_MOTIVO_PAGO_ID = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd'

const MOMENTO = '2026-10-05T15:00:00Z'

export const MOTIVOS_DE_ANULACION_DE_PAGO = {
  items: [
    { id: MOTIVO_PAGO_ID, nombre: 'Pago rechazado o devuelto' },
    { id: OTRO_MOTIVO_PAGO_ID, nombre: 'Error de carga' },
  ],
}

export const PAGO_REGISTRADO = { pago_id: PAGO_ID, estado: 'CONFIRMADA', importe: '100000.00', saldo: '53720.00' }

export function pagoResumen(campos: Partial<Record<string, unknown>> = {}) {
  return {
    pago_id: PAGO_ID,
    fecha: '2026-10-05',
    proveedor_id: PROVEEDOR_ID,
    proveedor_nombre: 'Bodega Sur',
    importe: '100000.00',
    origen: 'INDEPENDIENTE',
    estado: 'CONFIRMADA',
    compra_id: null,
    ...campos,
  }
}

export function pagoDetalle(campos: Partial<Record<string, unknown>> = {}) {
  return {
    ...pagoResumen(),
    observacion: 'Paga facturas 0001-123',
    compra_estado: null,
    medios: [
      { medio_pago_id: EFECTIVO_ID, medio_nombre: 'Efectivo', importe: '60000.00', referencia: null },
      { medio_pago_id: TRANSFERENCIA_ID, medio_nombre: 'Transferencia', importe: '40000.00', referencia: '0042' },
    ],
    anulacion: null,
    ...campos,
  }
}

export const ANULACION_DE_PAGO = {
  motivo_id: MOTIVO_PAGO_ID,
  motivo_nombre: 'Pago rechazado o devuelto',
  anulado_por_id: 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1',
  anulado_por_nombre: 'Marta Anuladora',
  anulado_en: MOMENTO,
}

export function reglaSaldo(saldo: string, proveedorId = PROVEEDOR_ID): ReglaDeApi {
  return { metodo: 'GET', ruta: `/proveedores/${proveedorId}/saldo`, responder: () => ({ status: 200, cuerpo: { saldo } }) }
}

/** Reglas de lectura que necesitan las pantallas de pagos. */
export function reglasBase(saldo = '153720.00'): ReglaDeApi[] {
  return [
    {
      metodo: 'GET',
      ruta: '/proveedores/opciones',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: PROVEEDOR_ID, nombre: 'Bodega Sur' }], cursor_siguiente: null } }),
    },
    reglaSaldo(saldo),
    { metodo: 'GET', ruta: '/configuracion/medios-pago', responder: () => ({ status: 200, cuerpo: MEDIOS_DE_PAGO }) },
    { metodo: 'GET', ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: MOTIVOS_DE_ANULACION_DE_PAGO }) },
  ]
}

export function montarApi(apiFetchMock: Mock, extra: ReglaDeApi[] = [], saldo = '153720.00'): void {
  enrutar(apiFetchMock, [...extra, ...reglasBase(saldo)])
}

export function fechaDeHoyParaPruebas(): string {
  const ahora = new Date()
  const mes = String(ahora.getMonth() + 1).padStart(2, '0')
  const dia = String(ahora.getDate()).padStart(2, '0')
  return `${String(ahora.getFullYear())}-${mes}-${dia}`
}
