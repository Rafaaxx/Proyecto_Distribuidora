import type { Mock } from 'vitest'

import { enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'
import { EFECTIVO_ID, MEDIOS_DE_PAGO, TRANSFERENCIA_ID } from '../compras/comprasDePrueba'

export { EFECTIVO_ID, TRANSFERENCIA_ID }

/**
 * Datos y reglas de API compartidos por las pruebas de las pantallas de ventas (change 18a,
 * grupo 12). `Kiosco La Esquina` debe $150.000,00; Vino A cuesta $12.500,00 por 6 unidades.
 */

export const VENTA_ID = '77777777-7777-4777-8777-777777777777'
export const CLIENTE_ID = '11111111-1111-4111-8111-111111111111'
export const OTRO_CLIENTE_ID = '12121212-1212-4121-8121-121212121212'
export const CONSUMIDOR_FINAL_ID = '13131313-1313-4131-8131-131313131313'
export const USUARIO_ID = 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1'
export const UBICACION_ID = '33333333-3333-4333-8333-333333333333'
export const JORNADA_ID = '88888888-8888-4888-8888-888888888888'
export const COBRANZA_ID = '55555555-5555-4555-8555-555555555555'
export const LISTA_ID = '44444444-4444-4444-8444-444444444444'
export const OTRA_LISTA_ID = '45454545-4545-4545-8545-454545454545'
export const VERSION_ID = '66666666-6666-4666-8666-666666666666'
export const VERSION_ANTERIOR_ID = '67676767-6767-4676-8676-676767676767'
export const MOTIVO_LISTA_ID = 'abababab-abab-4bab-8bab-abababababab'
export const VINO_ID = '99999999-9999-4999-8999-999999999991'
export const SIDRA_ID = '99999999-9999-4999-8999-999999999992'
export const PRESENTACION_BOTELLA_ID = '98989898-9898-4989-8989-989898989801'
export const PRESENTACION_CAJA_ID = '98989898-9898-4989-8989-989898989802'

const MOMENTO = '2026-10-20T15:00:00Z'

export const NUMERACION = { prefijo: 'V01', ultimo_correlativo: 41, siguiente_numero: 'V01-000042' }

export const VINO_A = {
  producto_id: VINO_ID,
  codigo: 'P-001',
  nombre: 'Vino A',
  precio_referencia: '12500.00',
  unidades_referencia: 6,
  sin_precio: false,
  stock_base: 48,
  presentaciones: [
    { presentacion_id: PRESENTACION_BOTELLA_ID, nombre: 'Botella', unidades_base: 1, es_referencia: false },
    { presentacion_id: PRESENTACION_CAJA_ID, nombre: 'Caja x6', unidades_base: 6, es_referencia: true },
  ],
}

export const SIDRA_SIN_PRECIO = {
  producto_id: SIDRA_ID,
  codigo: 'P-002',
  nombre: 'Sidra',
  precio_referencia: null,
  unidades_referencia: null,
  sin_precio: true,
  stock_base: 10,
  presentaciones: [{ presentacion_id: '98989898-9898-4989-8989-989898989803', nombre: 'Botella', unidades_base: 1, es_referencia: true }],
}

export function respuestaDePrecios(items: unknown[], campos: Record<string, unknown> = {}) {
  return {
    lista_id: LISTA_ID,
    lista_nombre: 'Mayorista',
    version_id: VERSION_ID,
    version_numero: 2,
    ubicacion_id: UBICACION_ID,
    items,
    cursor_siguiente: null,
    ...campos,
  }
}

export const VENTA_CONFIRMADA = {
  venta_id: VENTA_ID,
  numero: 'V01-000042',
  estado: 'CONFIRMADA',
  total: '31250.00',
  saldo: '161250.00',
  cobranza_id: COBRANZA_ID,
}

export function ventaResumen(campos: Partial<Record<string, unknown>> = {}) {
  return {
    venta_id: VENTA_ID,
    numero: 'V01-000042',
    occurred_at: MOMENTO,
    cliente_id: CLIENTE_ID,
    cliente_nombre: 'Kiosco La Esquina',
    usuario_id: USUARIO_ID,
    usuario_nombre: 'Juan Vendedor',
    ubicacion_id: UBICACION_ID,
    ubicacion_nombre: 'Depósito central',
    jornada_id: null,
    total: '31250.00',
    estado: 'CONFIRMADA',
    estado_facturacion: 'SIN_FACTURAR',
    modo_confirmacion: 'ONLINE',
    ...campos,
  }
}

export const LINEA_CAJAS = {
  linea_id: 'l1',
  orden: 0,
  producto_id: VINO_ID,
  producto_nombre: 'Vino A',
  presentacion_id: PRESENTACION_CAJA_ID,
  presentacion_nombre: 'Caja x6',
  lista_version_id: VERSION_ID,
  unidades_presentacion: 6,
  cantidad: 2,
  cantidad_base: 12,
  precio_referencia: '12500.00',
  unidades_referencia: 6,
  importe_bruto: '25000.00',
  importe_descuento: '0.00',
  importe_neto: '25000.00',
  alicuota: '0.000000',
  importe_iva: '0.00',
  costo_unitario: null,
  costo_total: null,
  // Change 18b: la API siempre trae los descuentos congelados de la línea (vacío sin descuentos).
  descuentos: [] as unknown[],
}

export const LINEA_BOTELLAS = {
  ...LINEA_CAJAS,
  linea_id: 'l2',
  orden: 1,
  presentacion_id: PRESENTACION_BOTELLA_ID,
  presentacion_nombre: 'Botella',
  unidades_presentacion: 1,
  cantidad: 3,
  cantidad_base: 3,
  importe_bruto: '6250.00',
  importe_neto: '6250.00',
}

export function ventaDetalle(campos: Partial<Record<string, unknown>> = {}) {
  return {
    ...ventaResumen(),
    registered_at: MOMENTO,
    dispositivo_id: 'dddddddd-0000-4000-8000-000000000001',
    lista_id: LISTA_ID,
    lista_nombre: 'Mayorista',
    version_id: VERSION_ID,
    version_numero: 2,
    motivo_lista: null,
    modo_impositivo: 'A',
    total_neto: '31250.00',
    total_iva: '0.00',
    importe_facturado: '0.00',
    cobranza: { cobranza_id: COBRANZA_ID, importe: '20000.00', estado: 'CONFIRMADA' },
    lineas: [LINEA_CAJAS, LINEA_BOTELLAS],
    observaciones: [],
    // Change 18b: nulo en una venta anterior al change (sin snapshot de crédito).
    credito: null,
    ...campos,
  }
}

export const UBICACIONES = {
  items: [
    { id: UBICACION_ID, nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true, actualizado_en: MOMENTO, jornada: null },
  ],
  cursor_siguiente: null,
}

export const JORNADA_ABIERTA = {
  id: JORNADA_ID,
  ubicacion_id: '34343434-3434-4343-8343-343434343434',
  ubicacion_nombre: 'Camioneta 2',
  usuario_id: USUARIO_ID,
  usuario_nombre: 'Juan Vendedor',
  dispositivo_id: 'dddddddd-0000-4000-8000-000000000001',
  estado: 'ABIERTA',
  abierta_en: MOMENTO,
  rendida_en: null,
  rendida_por_id: null,
  rendida_por_nombre: null,
  cerrada_en: null,
}

export const MOTIVOS_DE_LISTA_ANTERIOR = {
  items: [
    { id: MOTIVO_LISTA_ID, nombre: 'Precio acordado con el cliente' },
    { id: 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd', nombre: 'Otro' },
  ],
}

export function reglaSaldo(saldo: string, clienteId = CLIENTE_ID): ReglaDeApi {
  return { metodo: 'GET', ruta: `/clientes/${clienteId}/saldo`, responder: () => ({ status: 200, cuerpo: { saldo } }) }
}

/** Reglas de lectura que necesita la pantalla "Nueva venta" (sin jornada abierta por defecto). */
export function reglasBase(saldo = '150000.00'): ReglaDeApi[] {
  return [
    {
      metodo: 'GET',
      ruta: '/clientes/opciones',
      responder: (url) => ({
        status: 200,
        cuerpo: {
          items: [
            { id: CLIENTE_ID, nombre: 'Kiosco La Esquina', codigo: 'C-001', estado: 'ACTIVO', es_consumidor_final: false },
            { id: OTRO_CLIENTE_ID, nombre: 'Almacén Don Pedro', codigo: 'C-002', estado: 'SUSPENDIDO', es_consumidor_final: false },
            // El servidor ofrece el consumidor final solo si se lo pide (CLI-03).
            ...(url.searchParams.get('incluir_consumidor_final') === 'true'
              ? [{ id: CONSUMIDOR_FINAL_ID, nombre: 'Consumidor final', codigo: null, estado: 'ACTIVO', es_consumidor_final: true }]
              : []),
          ],
          cursor_siguiente: null,
        },
      }),
    },
    reglaSaldo(saldo),
    reglaSaldo('0.00', CONSUMIDOR_FINAL_ID),
    { metodo: 'GET', ruta: '/ventas/numeracion', responder: () => ({ status: 200, cuerpo: NUMERACION }) },
    { metodo: 'GET', ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
    { metodo: 'GET', ruta: '/stock/jornadas/actual', responder: () => ({ status: 404, cuerpo: { title: 'Sin jornada', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    {
      metodo: 'GET',
      ruta: '/ventas/precios',
      responder: (url) => {
        const q = (url.searchParams.get('q') ?? '').toLowerCase()
        const productoId = url.searchParams.get('producto_id')
        const todos = [VINO_A, SIDRA_SIN_PRECIO]
        const items = todos.filter(
          (p) => (productoId === null || p.producto_id === productoId) && (q === '' || p.nombre.toLowerCase().includes(q)),
        )
        return { status: 200, cuerpo: respuestaDePrecios(items) }
      },
    },
    { metodo: 'GET', ruta: '/precios/listas/opciones', responder: () => ({ status: 200, cuerpo: { items: [{ id: LISTA_ID, nombre: 'Mayorista' }, { id: OTRA_LISTA_ID, nombre: 'Minorista' }] } }) },
    { metodo: 'GET', ruta: '/configuracion/medios-pago', responder: () => ({ status: 200, cuerpo: MEDIOS_DE_PAGO }) },
    { metodo: 'GET', ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: MOTIVOS_DE_LISTA_ANTERIOR }) },
    {
      metodo: 'GET',
      ruta: '/ventas/versiones',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            { version_id: VERSION_ID, numero: 2, estado: 'VIGENTE', vigencia_desde: MOMENTO, vigencia_hasta: null },
            { version_id: VERSION_ANTERIOR_ID, numero: 1, estado: 'HISTORICA', vigencia_desde: '2026-01-01T00:00:00Z', vigencia_hasta: MOMENTO },
          ],
        },
      }),
    },
  ]
}

export function montarApi(apiFetchMock: Mock, extra: ReglaDeApi[] = [], saldo = '150000.00'): void {
  enrutar(apiFetchMock, [...extra, ...reglasBase(saldo)])
}
