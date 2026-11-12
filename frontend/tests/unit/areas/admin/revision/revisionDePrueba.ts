import type { Mock } from 'vitest'

import { enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'

/**
 * Datos y reglas de API compartidos por las pruebas de la revisión (change 25, grupos 13 a 15).
 * Juan vendió a Kiosco La Esquina sin conexión; la Supervisora revisa.
 */

export const VENTA_ID = '11111111-1111-4111-8111-111111111111'
export const COBRANZA_ID = '22222222-2222-4222-8222-222222222222'
export const OBS_STOCK_1 = 'a0000000-0000-4000-8000-000000000001'
export const OBS_STOCK_2 = 'a0000000-0000-4000-8000-000000000002'
export const OBS_DESCUENTO = 'a0000000-0000-4000-8000-000000000003'
export const OBS_MEDIO = 'a0000000-0000-4000-8000-000000000004'
export const USUARIO_JUAN = 'b0000000-0000-4000-8000-000000000001'
export const JORNADA_ID = 'c0000000-0000-4000-8000-000000000001'
export const DISPOSITIVO_ID = 'd0000000-0000-4000-8000-000000000001'
export const RECHAZO_ID = 'e0000000-0000-4000-8000-000000000001'
export const CUARENTENA_ID = 'e0000000-0000-4000-8000-000000000002'
export const VENTA_VINCULADA_ID = 'f0000000-0000-4000-8000-000000000001'
export const COBRANZA_VINCULADA_ID = 'f0000000-0000-4000-8000-000000000002'

export function observacion(campos: Partial<Record<string, unknown>> = {}) {
  return {
    id: OBS_STOCK_1,
    codigo: 'STOCK_NEGATIVO',
    detalle: { linea_id: 'l1', saldo_resultante: -3 },
    estado: 'PENDIENTE',
    resuelto_por_id: null,
    resuelto_por_nombre: null,
    resuelto_en: null,
    comentario: null,
    ...campos,
  }
}

export function operacion(campos: Partial<Record<string, unknown>> = {}) {
  return {
    operacion_tipo: 'VENTA',
    operacion_id: VENTA_ID,
    estado: 'PENDIENTE',
    resumen: { titulo: 'Venta 0001-00000012', tercero: 'Kiosco La Esquina', total: '12500.00', momento: '2026-11-04T15:00:00Z' },
    usuario_id: USUARIO_JUAN,
    usuario_nombre: 'Juan',
    dispositivo_id: DISPOSITIVO_ID,
    jornada_id: JORNADA_ID,
    modo: 'OFFLINE',
    occurred_at: '2026-11-04T15:00:00Z',
    registered_at: '2026-11-04T18:00:00Z',
    observaciones: [
      observacion(),
      observacion({ id: OBS_STOCK_2, detalle: { linea_id: 'l2', saldo_resultante: -8 } }),
      observacion({ id: OBS_DESCUENTO, codigo: 'DESCUENTO_DIFIERE', detalle: { causas: [{ causa: 'MOTIVO' }] } }),
    ],
    ...campos,
  }
}

export function rechazo(campos: Partial<Record<string, unknown>> = {}) {
  return {
    origen: 'RECHAZO',
    id: RECHAZO_ID,
    operation_id: '99999999-9999-4999-8999-999999999991',
    tipo: 'VENTA_CONFIRMAR',
    estado: 'PENDIENTE',
    codigo: 'VENTA_SIN_LINEAS',
    usuario_id: USUARIO_JUAN,
    usuario_nombre: 'Juan',
    dispositivo_id: DISPOSITIVO_ID,
    jornada_id: JORNADA_ID,
    recibido_en: '2026-11-04T18:00:00Z',
    occurred_at: '2026-11-04T15:00:00Z',
    aceptada_despues: false,
    resumen: {
      titulo: 'Venta',
      cliente: 'Kiosco La Esquina',
      numero: '0001-00000013',
      total: '8000.00',
      lineas: [{ producto: 'Gaseosa 2 L', cantidad: 4, importe: '8000.00' }],
      medios: [{ medio: 'Efectivo', importe: '8000.00' }],
    },
    resuelto_por_id: null,
    resuelto_por_nombre: null,
    resuelto_en: null,
    comentario: null,
    vinculo_tipo: null,
    vinculo_id: null,
    ...campos,
  }
}

export const pagina = (items: unknown[], cursor: string | null = null) => ({ items, cursor_siguiente: cursor })

export const RESUMEN_VACIO = {
  observaciones_por_codigo: {},
  observaciones_pendientes: 0,
  rechazos_pendientes: 0,
  cuarentenas_pendientes: 0,
  total_pendiente: 0,
}

export function montarApi(apiFetchMock: Mock, reglas: ReglaDeApi[] = []): void {
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/observaciones/resumen', responder: () => ({ status: 200, cuerpo: RESUMEN_VACIO }) },
    ...reglas,
  ])
}
