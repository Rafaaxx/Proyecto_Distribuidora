import type { Mock } from 'vitest'

import { enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'

/**
 * Datos y reglas de API compartidos por las pruebas de las pantallas de listas de precios
 * (change 13, grupo 13). Vino A: Caja x6 de referencia, 9.500,00 en el borrador, 8.600,00 en la
 * versión base; costo de referencia 6.600,00 con markup 30% (`01` §7.2).
 */

export const LISTA_ID = '11111111-1111-4111-8111-111111111111'
export const OTRA_LISTA_ID = '12121212-1212-4121-8121-121212121212'
export const VERSION_BORRADOR_ID = '22222222-2222-4222-8222-222222222222'
export const VERSION_VIGENTE_ID = '23232323-2323-4232-8232-232323232323'
export const VERSION_PROGRAMADA_ID = '24242424-2424-4242-8242-242424242424'
export const VERSION_ANTERIOR_ID = '25252525-2525-4252-8252-252525252525'
export const VINO_A_ID = '33333333-3333-4333-8333-333333333333'
export const CERVEZA_B_ID = '34343434-3434-4343-8343-343434343434'
export const GASEOSA_C_ID = '35353535-3535-4353-8353-353535353535'
export const CATEGORIA_VINOS_ID = '44444444-4444-4444-8444-444444444444'
export const CATEGORIA_CERVEZAS_ID = '45454545-4545-4545-8545-454545454545'
export const REGLA_ID = '55555555-5555-4555-8555-555555555555'
export const REGLA_LISTA_ID = '56565656-5656-4565-8565-565656565656'

const MOMENTO = '2026-10-05T15:00:00Z'

export function lista(campos: Partial<Record<string, unknown>> = {}) {
  return {
    id: LISTA_ID,
    nombre: 'General',
    redondeo_multiplo: '100.00',
    redondeo_direccion: 'ARRIBA',
    activo: true,
    version_vigente: 3,
    tiene_borrador: true,
    creado_en: MOMENTO,
    actualizado_en: MOMENTO,
    ...campos,
  }
}

export function listaDetalle(campos: Partial<Record<string, unknown>> = {}) {
  return {
    ...lista(),
    redondeos_categoria: [
      {
        id: '66666666-6666-4666-8666-666666666666',
        categoria_id: CATEGORIA_VINOS_ID,
        categoria_nombre: 'Vinos',
        multiplo: '50.00',
        direccion: 'CERCANO',
        activo: true,
      },
    ],
    ...campos,
  }
}

export function regla(campos: Partial<Record<string, unknown>> = {}) {
  return {
    id: REGLA_ID,
    lista_id: LISTA_ID,
    alcance_tipo: 'CATEGORIA',
    alcance_id: CATEGORIA_VINOS_ID,
    alcance_nombre: 'Vinos',
    tipo: 'MARKUP',
    valor: '0.300000',
    activo: true,
    creado_en: MOMENTO,
    actualizado_en: MOMENTO,
    ...campos,
  }
}

export const REGLA_DE_LISTA = regla({
  id: REGLA_LISTA_ID,
  alcance_tipo: 'LISTA',
  alcance_id: null,
  alcance_nombre: null,
  tipo: 'MARGEN_BRUTO',
  valor: '0.300000',
})

export function version(campos: Partial<Record<string, unknown>> = {}) {
  return {
    id: VERSION_VIGENTE_ID,
    lista_id: LISTA_ID,
    numero: 3,
    estado: 'PUBLICADA',
    estado_derivado: 'VIGENTE',
    vigencia_desde: '2026-09-01T03:00:00Z',
    vigencia_hasta: null,
    version_base_id: VERSION_ANTERIOR_ID,
    generado_en: '2026-08-30T12:00:00Z',
    creado_por_id: 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1',
    creado_por_nombre: 'Marta Gestora',
    creado_en: '2026-08-30T12:00:00Z',
    publicado_por_id: 'b2b2b2b2-b2b2-42b2-82b2-b2b2b2b2b2b2',
    publicado_por_nombre: 'Pedro Publicador',
    publicado_en: '2026-08-31T12:00:00Z',
    anulado_por_id: null,
    anulado_por_nombre: null,
    anulado_en: null,
    ...campos,
  }
}

export const VERSION_BORRADOR = version({
  id: VERSION_BORRADOR_ID,
  numero: 4,
  estado: 'BORRADOR',
  estado_derivado: null,
  vigencia_desde: null,
  version_base_id: VERSION_VIGENTE_ID,
  generado_en: '2026-10-05T15:00:00Z',
  publicado_por_id: null,
  publicado_por_nombre: null,
  publicado_en: null,
})

export const VERSION_PROGRAMADA = version({
  id: VERSION_PROGRAMADA_ID,
  numero: 5,
  estado_derivado: 'PROGRAMADA',
  vigencia_desde: '2026-12-01T03:00:00Z',
})

export const VERSION_HISTORICA = version({
  id: VERSION_ANTERIOR_ID,
  numero: 2,
  estado_derivado: 'HISTORICA',
  vigencia_desde: '2026-07-01T03:00:00Z',
  version_base_id: null,
})

export const SENALES_NINGUNA = {
  sin_costo: false,
  margen_menor: false,
  costo_otra_regla_iva: false,
  costos_distintos_por_presentacion: false,
  presentacion_del_costo_id: null,
  presentacion_del_costo_nombre: null,
}

export function precio(campos: Partial<Record<string, unknown>> = {}) {
  return {
    producto_id: VINO_A_ID,
    producto_nombre: 'Vino A',
    unidades_referencia: 6,
    precio_final: '9500.00',
    manual: false,
    precio_version_base: '8600.00',
    relacion: 'CAMBIA',
    senales: SENALES_NINGUNA,
    presentaciones: [
      { nombre: 'Botella', unidades_base: 1 },
      { nombre: 'Caja x6', unidades_base: 6 },
    ],
    costo_referencia: '6600.000000',
    tipo_margen: 'MARKUP',
    valor_margen: '0.300000',
    precio_calculado: '8580.000000',
    ...campos,
  }
}

export const PRECIO_MANUAL_CON_SENAL = precio({
  producto_id: CERVEZA_B_ID,
  producto_nombre: 'Cerveza B',
  unidades_referencia: 12,
  precio_final: '31000.00',
  manual: true,
  precio_version_base: '31200.00',
  relacion: 'CAMBIA',
  senales: { ...SENALES_NINGUNA, margen_menor: true },
  presentaciones: [
    { nombre: 'Lata', unidades_base: 1 },
    { nombre: 'Caja x12', unidades_base: 12 },
  ],
  costo_referencia: '21780.000000',
  precio_calculado: '31168.000000',
})

export function borrador(campos: Partial<Record<string, unknown>> = {}) {
  return {
    version: VERSION_BORRADOR,
    precios: [precio(), PRECIO_MANUAL_CON_SENAL],
    siguiente_cursor: null,
    productos_sin_precio: [{ producto_id: GASEOSA_C_ID, producto_nombre: 'Gaseosa C', causa: 'SIN_COSTO' }],
    ...campos,
  }
}

export function borradorSinCostos() {
  return borrador({
    precios: [
      precio({ costo_referencia: null, tipo_margen: null, valor_margen: null, precio_calculado: null }),
      { ...PRECIO_MANUAL_CON_SENAL, costo_referencia: null, tipo_margen: null, valor_margen: null, precio_calculado: null },
    ],
  })
}

export const OPCIONES_DE_LISTAS = {
  items: [
    { id: LISTA_ID, nombre: 'General' },
    { id: OTRA_LISTA_ID, nombre: 'Mayorista' },
  ],
}

export function respuestaDeApi(status: number, cuerpo: unknown) {
  return { status, cuerpo }
}

/** Reglas de lectura mínimas para las pantallas de detalle y de alcance de reglas. */
export function reglasDeCatalogo(): ReglaDeApi[] {
  return [
    {
      metodo: 'GET',
      ruta: '/catalogo/categorias',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            { id: CATEGORIA_VINOS_ID, nombre: 'Vinos', activo: true, creado_en: MOMENTO, actualizado_en: MOMENTO },
            { id: CATEGORIA_CERVEZAS_ID, nombre: 'Cervezas', activo: true, creado_en: MOMENTO, actualizado_en: MOMENTO },
          ],
          cursor_siguiente: null,
        },
      }),
    },
    { metodo: 'GET', ruta: '/catalogo/marcas', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
    {
      metodo: 'GET',
      ruta: '/catalogo/productos',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            {
              id: VINO_A_ID,
              codigo: 'VIN-A',
              nombre: 'Vino A',
              categoria_id: CATEGORIA_VINOS_ID,
              marca_id: null,
              proveedor_id: 'p1',
              unidad_base: 'unidad',
              alicuota_id: 'a1',
              activo: true,
              creado_en: MOMENTO,
              actualizado_en: MOMENTO,
            },
          ],
          cursor_siguiente: null,
        },
      }),
    },
    {
      metodo: 'GET',
      ruta: '/proveedores/opciones',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: 'p1', nombre: 'Bodega Sur' }], cursor_siguiente: null } }),
    },
  ]
}

/** Reglas de lectura del detalle de una lista (lista, reglas, versiones, catálogo). */
export function reglasDeDetalle(): ReglaDeApi[] {
  return [
    { metodo: 'GET', ruta: `/precios/listas/${LISTA_ID}`, responder: () => ({ status: 200, cuerpo: listaDetalle() }) },
    {
      metodo: 'GET',
      ruta: `/precios/listas/${LISTA_ID}/reglas`,
      responder: () => ({ status: 200, cuerpo: { items: [regla(), REGLA_DE_LISTA] } }),
    },
    {
      metodo: 'GET',
      ruta: `/precios/listas/${LISTA_ID}/versiones`,
      responder: () => ({
        status: 200,
        cuerpo: { items: [VERSION_BORRADOR, VERSION_PROGRAMADA, version(), VERSION_HISTORICA] },
      }),
    },
    ...reglasDeCatalogo(),
  ]
}

export function montarApi(apiFetchMock: Mock, reglas: ReglaDeApi[]): void {
  enrutar(apiFetchMock, reglas)
}

/**
 * Reglas de lectura de la pantalla del borrador (borrador y lista). El borrador trae las
 * presentaciones de cada producto (ajuste B): no hay lectura de detalle por producto.
 */
export function reglasDeBorrador(cuerpoDelBorrador: unknown = borrador()): ReglaDeApi[] {
  return [
    { metodo: 'GET', ruta: `/precios/listas/${LISTA_ID}/borrador`, responder: () => ({ status: 200, cuerpo: cuerpoDelBorrador }) },
    { metodo: 'GET', ruta: `/precios/listas/${LISTA_ID}`, responder: () => ({ status: 200, cuerpo: listaDetalle() }) },
  ]
}
