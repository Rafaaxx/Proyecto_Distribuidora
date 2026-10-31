import Dexie, { type EntityTable, type Table } from 'dexie'

import type { components } from '../../api/schema.gen'

/**
 * Base local Dexie/IndexedDB (`docs/02-arquitectura.md` §13.2).
 *
 * Versión 1 (change 03): solo `meta`, con el identificador de dispositivo.
 * Versión 2 (change 21, `design.md` D10): agrega las tablas MAESTRAS que llena el bootstrap.
 * `ventas`, `cobranzas`, `movimientos_locales` y `cola` llegan con el change 22a (versión 3),
 * cuando tengan consumidor. Los importes siguen siendo string (INV-03) y las cantidades,
 * enteros en unidad base (INV-04).
 */
type Esquema = components['schemas']

export interface RegistroMeta {
  clave: string
  valor: string
}

/** Fila única (`clave = 'actual'`): usuario, permisos, jornada, numeración y contexto de venta. */
export interface SesionLocal {
  clave: 'actual'
  usuario: Esquema['SesionBootstrap']['usuario']
  permisos: string[]
  jornada: Esquema['SesionBootstrap']['jornada']
  numeracion: Esquema['SesionBootstrap']['numeracion']
  contexto_venta: Esquema['ContextoVentaBootstrap'] | null
}

/** Fila única (`clave = 'organizacion'`): parámetros de la organización. */
export type ConfiguracionLocal = Esquema['ConfiguracionBootstrap'] & { clave: 'organizacion' }

export type ProductoLocal = Omit<Esquema['ProductoBootstrap'], 'presentaciones'>

export type PresentacionLocal = Esquema['PresentacionBootstrap'] & { producto_id: string }

/** Incluye el saldo al momento del bootstrap y el crédito resuelto. */
export type ClienteLocal = Esquema['ClienteBootstrap']

export interface ListaLocal {
  id: string
  nombre: string
  es_predeterminada: boolean
}

export interface VersionLocal {
  id: string
  lista_id: string
  numero: number
  estado: string
  vigencia_desde: string
  vigencia_hasta: string | null
}

export interface PrecioLocal {
  version_id: string
  producto_id: string
  precio_referencia: string
  unidades_referencia: number
}

export type ReglaDescuentoLocal = Esquema['ReglaDescuentoBootstrap']

export type StockLocal = Esquema['StockBootstrap']

export type AutorizadorLocal = Esquema['AutorizadorBootstrap']

export type CatalogoLocal =
  | { clave: 'medios_pago'; items: Esquema['MedioPagoBootstrap'][] }
  | { clave: 'motivos'; items: Esquema['MotivoBootstrap'][] }
  | { clave: 'alicuotas'; items: Esquema['AlicuotaBootstrap'][] }

class BaseLocal extends Dexie {
  meta!: EntityTable<RegistroMeta, 'clave'>
  sesion!: EntityTable<SesionLocal, 'clave'>
  configuracion!: EntityTable<ConfiguracionLocal, 'clave'>
  productos!: EntityTable<ProductoLocal, 'id'>
  presentaciones!: EntityTable<PresentacionLocal, 'id'>
  clientes!: EntityTable<ClienteLocal, 'id'>
  listas!: EntityTable<ListaLocal, 'id'>
  versiones!: EntityTable<VersionLocal, 'id'>
  precios!: Table<PrecioLocal, [string, string]>
  reglas_descuento!: EntityTable<ReglaDescuentoLocal, 'id'>
  stock!: EntityTable<StockLocal, 'producto_id'>
  autorizadores!: EntityTable<AutorizadorLocal, 'id'>
  catalogos!: EntityTable<CatalogoLocal, 'clave'>

  constructor() {
    super('distribuidora')
    this.version(1).stores({
      meta: 'clave',
    })
    this.version(2).stores({
      meta: 'clave',
      sesion: 'clave',
      configuracion: 'clave',
      productos: 'id',
      presentaciones: 'id, producto_id',
      clientes: 'id',
      listas: 'id',
      versiones: 'id, lista_id',
      precios: '[version_id+producto_id], version_id',
      reglas_descuento: 'id',
      stock: 'producto_id',
      autorizadores: 'id',
      catalogos: 'clave',
    })
  }
}

/** Tablas maestras que el bootstrap reemplaza (lista explícita, D10): nada más se toca. */
export const TABLAS_MAESTRAS = [
  'sesion',
  'configuracion',
  'productos',
  'presentaciones',
  'clientes',
  'listas',
  'versiones',
  'precios',
  'reglas_descuento',
  'stock',
  'autorizadores',
  'catalogos',
] as const

export const baseLocal = new BaseLocal()
