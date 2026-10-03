import type { Mock } from 'vitest'

import { enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'

/**
 * Datos y reglas de API compartidos por las pruebas de las pantallas de compras
 * (change 11, grupo 12). Caja x12 de `Cerveza B` con IVA 21 % es el caso de
 * `cmp-02-compra.json`: costo base `1.239,669421`, neto `14.876,03`.
 */

export const PROVEEDOR_ID = '11111111-1111-4111-8111-111111111111'
export const UBICACION_ID = '33333333-3333-4333-8333-333333333333'
export const CERVEZA_B_ID = '22222222-2222-4222-8222-222222222222'
export const VINO_A_ID = '44444444-4444-4444-8444-444444444444'
export const CAJA_X12_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
export const BOTELLA_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
export const CAJA_X6_SOLO_VENTA_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
export const ALICUOTA_21_ID = '77777777-7777-4777-8777-777777777777'
export const ALICUOTA_0_ID = '88888888-8888-4888-8888-888888888888'
export const EFECTIVO_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
export const TRANSFERENCIA_ID = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
export const MOTIVO_ID = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
export const COMPRA_ID = '99999999-9999-4999-8999-999999999999'

const MOMENTO = '2026-01-01T00:00:00Z'

function producto(id: string, codigo: string, nombre: string, alicuotaId: string) {
  return {
    id,
    codigo,
    nombre,
    categoria_id: 'c1',
    marca_id: null,
    proveedor_id: PROVEEDOR_ID,
    unidad_base: 'unidad',
    alicuota_id: alicuotaId,
    activo: true,
    creado_en: MOMENTO,
    actualizado_en: MOMENTO,
  }
}

function presentacion(id: string, productoId: string, nombre: string, unidades: number, usarEnCompra: boolean, esReferencia: boolean) {
  return {
    id,
    producto_id: productoId,
    nombre,
    unidades_base: unidades,
    usar_en_venta: true,
    usar_en_compra: usarEnCompra,
    es_referencia: esReferencia,
    activo: true,
    creado_en: MOMENTO,
    actualizado_en: MOMENTO,
  }
}

export const PRODUCTO_CERVEZA_B = producto(CERVEZA_B_ID, 'CER-B', 'Cerveza B', ALICUOTA_21_ID)
export const PRODUCTO_VINO_A = producto(VINO_A_ID, 'VIN-A', 'Vino A', ALICUOTA_0_ID)

export const DETALLE_CERVEZA_B = {
  ...PRODUCTO_CERVEZA_B,
  proveedor_nombre: 'Bodega Sur',
  presentaciones: [presentacion(CAJA_X12_ID, CERVEZA_B_ID, 'Caja x12', 12, true, true)],
}

export const DETALLE_VINO_A = {
  ...PRODUCTO_VINO_A,
  proveedor_nombre: 'Bodega Sur',
  presentaciones: [
    presentacion(BOTELLA_ID, VINO_A_ID, 'Botella', 1, true, true),
    presentacion(CAJA_X6_SOLO_VENTA_ID, VINO_A_ID, 'Caja x6', 6, false, false),
  ],
}

export const MEDIOS_DE_PAGO = {
  items: [
    { id: EFECTIVO_ID, nombre: 'Efectivo', requiere_referencia: false },
    { id: TRANSFERENCIA_ID, nombre: 'Transferencia', requiere_referencia: true },
  ],
}

export const COMPRA_CONFIRMADA = {
  compra_id: COMPRA_ID,
  total_neto: '14876.03',
  total_factura: '18000.00',
  pago_id: null,
  diferencias_de_costo: [] as unknown[],
}

/** Reglas de lectura que necesita el formulario de compra. */
export function reglasDelFormulario(): ReglaDeApi[] {
  return [
    {
      metodo: 'GET',
      ruta: '/proveedores/opciones',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: PROVEEDOR_ID, nombre: 'Bodega Sur' }], cursor_siguiente: null } }),
    },
    {
      metodo: 'GET',
      ruta: '/stock/ubicaciones',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [{ id: UBICACION_ID, nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true, actualizado_en: MOMENTO }],
          cursor_siguiente: null,
        },
      }),
    },
    {
      metodo: 'GET',
      ruta: '/catalogo/productos',
      responder: (url) => ({
        status: 200,
        cuerpo: {
          items: url.searchParams.get('proveedor_id') === PROVEEDOR_ID ? [PRODUCTO_CERVEZA_B, PRODUCTO_VINO_A] : [],
          cursor_siguiente: null,
        },
      }),
    },
    { metodo: 'GET', ruta: `/catalogo/productos/${CERVEZA_B_ID}`, responder: () => ({ status: 200, cuerpo: DETALLE_CERVEZA_B }) },
    { metodo: 'GET', ruta: `/catalogo/productos/${VINO_A_ID}`, responder: () => ({ status: 200, cuerpo: DETALLE_VINO_A }) },
    {
      metodo: 'GET',
      ruta: '/configuracion/alicuotas',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            { id: ALICUOTA_21_ID, nombre: 'IVA 21%', valor: '0.210000', activo: true },
            { id: ALICUOTA_0_ID, nombre: 'Exento', valor: '0.000000', activo: true },
          ],
          cursor_siguiente: null,
        },
      }),
    },
    { metodo: 'GET', ruta: '/configuracion/medios-pago', responder: () => ({ status: 200, cuerpo: MEDIOS_DE_PAGO }) },
  ]
}

export function montarApi(apiFetchMock: Mock, extra: ReglaDeApi[] = []): void {
  enrutar(apiFetchMock, [...extra, ...reglasDelFormulario()])
}
