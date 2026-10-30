import type { ReglaDeApi } from '../../../utils/enrutarApi'

/**
 * Datos y reglas de API compartidos por las pruebas de las pantallas de descuentos (change 16,
 * grupo 15). Ejemplo de `01` §10: cajas equivalentes >= 20 con 5 %, sobre toda la venta.
 */

export const REGLA_ID = '11111111-1111-4111-8111-111111111111'
export const OTRA_REGLA_ID = '12121212-1212-4121-8121-121212121212'
export const MARCA_ID = '33333333-3333-4333-8333-333333333333'
export const CATEGORIA_ID = '44444444-4444-4444-8444-444444444444'
export const PRODUCTO_ID = '55555555-5555-4555-8555-555555555555'
export const ROL_VENDEDOR_ID = '66666666-6666-4666-8666-666666666666'
export const ROL_SUPERVISOR_ID = '77777777-7777-4777-8777-777777777777'
export const ROL_ADMINISTRADOR_ID = '88888888-8888-4888-8888-888888888888'
export const ROL_ADMINISTRACION_ID = '99999999-9999-4999-8999-999999999999'

const MOMENTO = '2026-10-14T15:00:00Z'

export function regla(campos: Partial<Record<string, unknown>> = {}) {
  return {
    id: REGLA_ID,
    nombre: 'Mayorista 20 cajas',
    tipo: 'VOLUMEN_OPERACION',
    medida: 'CAJAS_EQUIVALENTES',
    operador: 'GTE',
    umbral: '20.0000',
    accion_tipo: 'PORCENTAJE',
    accion_porcentaje: '0.050000',
    accion_importe: null,
    prioridad: 10,
    acumulable: false,
    vigencia_desde: null,
    vigencia_hasta: null,
    estado: 'BORRADOR',
    alcances: [],
    creado_en: MOMENTO,
    actualizado_en: MOMENTO,
    ...campos,
  }
}

export function reglaDeMarca(campos: Partial<Record<string, unknown>> = {}) {
  return regla({
    id: OTRA_REGLA_ID,
    nombre: 'Coca-Cola importe fijo',
    tipo: 'VOLUMEN_ALCANCE',
    medida: 'IMPORTE_BRUTO',
    umbral: '100000.0000',
    accion_tipo: 'IMPORTE_FIJO',
    accion_porcentaje: null,
    accion_importe: '5000.00',
    acumulable: true,
    prioridad: 2,
    estado: 'ACTIVA',
    alcances: [{ tipo: 'MARCA', entidad_id: MARCA_ID, nombre: 'Coca-Cola' }],
    ...campos,
  })
}

export function rol(campos: Partial<Record<string, unknown>> = {}) {
  return { id: ROL_VENDEDOR_ID, nombre: 'Vendedor/Repartidor', activo: true, tope_descuento: '0.000000', permisos: ['DESCUENTO_MANUAL'], usuarios_activos: 0, usuarios_con_tope_propio: 0, usuarios_con_tope_propio_activos: 0, usuarios_con_tope_propio_inactivos: 0, ...campos }
}

export const ROLES = [
  rol({ id: ROL_ADMINISTRADOR_ID, nombre: 'Administrador', tope_descuento: '1.000000', permisos: ['DESCUENTO_MANUAL', 'ADMIN_USUARIOS'] }),
  rol({ id: ROL_SUPERVISOR_ID, nombre: 'Supervisor comercial', tope_descuento: '0.100000' }),
  rol({ id: ROL_VENDEDOR_ID, nombre: 'Vendedor/Repartidor', tope_descuento: '0.000000' }),
  rol({ id: ROL_ADMINISTRACION_ID, nombre: 'Administración', tope_descuento: '0.000000', permisos: ['VER_COSTOS'] }),
]

/** Lecturas del catálogo para elegir alcances (productos, categorías y marcas). */
export function reglasDeCatalogo(): ReglaDeApi[] {
  const base = { activo: true, creado_en: MOMENTO, actualizado_en: MOMENTO }
  return [
    {
      metodo: 'GET',
      ruta: '/catalogo/categorias',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: CATEGORIA_ID, nombre: 'Gaseosas', ...base }], cursor_siguiente: null } }),
    },
    {
      metodo: 'GET',
      ruta: '/catalogo/marcas',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: MARCA_ID, nombre: 'Coca-Cola', ...base }], cursor_siguiente: null } }),
    },
    {
      metodo: 'GET',
      ruta: '/catalogo/productos',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            {
              id: PRODUCTO_ID,
              codigo: 'VIN-A',
              nombre: 'Vino A',
              categoria_id: CATEGORIA_ID,
              marca_id: null,
              proveedor_id: 'p1',
              unidad_base: 'unidad',
              alicuota_id: 'a1',
              ...base,
            },
          ],
          cursor_siguiente: null,
        },
      }),
    },
  ]
}
