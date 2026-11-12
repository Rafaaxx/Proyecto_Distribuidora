import type { Mock } from 'vitest'

import { enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'
import { EFECTIVO_ID, MEDIOS_DE_PAGO, TRANSFERENCIA_ID } from '../compras/comprasDePrueba'

export { EFECTIVO_ID, TRANSFERENCIA_ID }

/**
 * Datos y reglas de API compartidos por las pruebas de las pantallas de cobranzas (change 17,
 * grupo 14). `Kiosco La Esquina` debe $150.000,00; `Almacén Don Pedro` es el otro cliente.
 */

export const COBRANZA_ID = '55555555-5555-4555-8555-555555555555'
export const COBRANZA_DE_VENTA_ID = '66666666-6666-4666-8666-666666666666'
export const CLIENTE_ID = '11111111-1111-4111-8111-111111111111'
export const OTRO_CLIENTE_ID = '12121212-1212-4121-8121-121212121212'
export const JORNADA_ID = '88888888-8888-4888-8888-888888888888'
export const USUARIO_ID = 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1'
export const MOTIVO_COBRANZA_ID = 'abababab-abab-4bab-8bab-abababababab'
export const OTRO_MOTIVO_COBRANZA_ID = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd'

const MOMENTO = '2026-10-05T15:00:00Z'

export const MOTIVOS_DE_ANULACION_DE_COBRANZA = {
  items: [
    { id: MOTIVO_COBRANZA_ID, nombre: 'Cheque rechazado' },
    { id: OTRO_MOTIVO_COBRANZA_ID, nombre: 'Error de carga' },
  ],
}

export const COBRANZA_REGISTRADA = {
  cobranza_id: COBRANZA_ID,
  estado: 'CONFIRMADA',
  importe: '50000.00',
  saldo: '100000.00',
  jornada_id: null,
}

export function cobranzaResumen(campos: Partial<Record<string, unknown>> = {}) {
  return {
    cobranza_id: COBRANZA_ID,
    occurred_at: MOMENTO,
    cliente_id: CLIENTE_ID,
    cliente_nombre: 'Kiosco La Esquina',
    importe: '50000.00',
    estado: 'CONFIRMADA',
    origen: 'INDEPENDIENTE',
    venta_id: null,
    usuario_id: USUARIO_ID,
    usuario_nombre: 'Juan Vendedor',
    jornada_id: null,
    ...campos,
  }
}

export function cobranzaDetalle(campos: Partial<Record<string, unknown>> = {}) {
  return {
    ...cobranzaResumen(),
    observacion: 'Pagó en mostrador',
    registered_at: MOMENTO,
    medios: [
      { medio_pago_id: EFECTIVO_ID, medio_nombre: 'Efectivo', importe: '30000.00', referencia: null },
      { medio_pago_id: TRANSFERENCIA_ID, medio_nombre: 'Transferencia', importe: '20000.00', referencia: '0042' },
    ],
    anulacion: null,
    observaciones: [],
    ...campos,
  }
}

export const ANULACION_DE_COBRANZA = {
  motivo_id: MOTIVO_COBRANZA_ID,
  motivo_nombre: 'Cheque rechazado',
  observacion: 'Volvió rechazado',
  usuario_id: USUARIO_ID,
  usuario_nombre: 'Marta Anuladora',
  anulada_en: MOMENTO,
}

export function reglaSaldo(saldo: string, clienteId = CLIENTE_ID): ReglaDeApi {
  return { metodo: 'GET', ruta: `/clientes/${clienteId}/saldo`, responder: () => ({ status: 200, cuerpo: { saldo } }) }
}

/** Reglas de lectura que necesitan las pantallas de cobranzas. */
export function reglasBase(saldo = '150000.00'): ReglaDeApi[] {
  return [
    {
      metodo: 'GET',
      ruta: '/clientes/opciones',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            { id: CLIENTE_ID, nombre: 'Kiosco La Esquina', codigo: 'C-001', estado: 'ACTIVO', es_consumidor_final: false },
            { id: OTRO_CLIENTE_ID, nombre: 'Almacén Don Pedro', codigo: 'C-002', estado: 'SUSPENDIDO', es_consumidor_final: false },
          ],
          cursor_siguiente: null,
        },
      }),
    },
    reglaSaldo(saldo),
    { metodo: 'GET', ruta: '/configuracion/medios-pago', responder: () => ({ status: 200, cuerpo: MEDIOS_DE_PAGO }) },
    { metodo: 'GET', ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: MOTIVOS_DE_ANULACION_DE_COBRANZA }) },
  ]
}

export function montarApi(apiFetchMock: Mock, extra: ReglaDeApi[] = [], saldo = '150000.00'): void {
  enrutar(apiFetchMock, [...extra, ...reglasBase(saldo)])
}
