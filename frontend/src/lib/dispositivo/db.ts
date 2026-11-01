import Dexie, { type EntityTable, type Table } from 'dexie'

import type { components } from '../../api/schema.gen'

/**
 * Base local Dexie/IndexedDB (`docs/02-arquitectura.md` §13.2).
 *
 * Versión 1 (change 03): solo `meta`, con el identificador de dispositivo.
 * Versión 2 (change 21, `design.md` D10): agrega las tablas MAESTRAS que llena el bootstrap.
 * Versión 3 (change 22a, `design.md` D3): agrega las tablas de OPERACIONES (`ventas`,
 * `cobranzas`, `movimientos_locales`, `cola`, `intentos_pin`) que el bootstrap NO toca
 * (`TABLAS_MAESTRAS` no cambia; `02` §13.4, SYN-09). Los importes siguen siendo string (INV-03)
 * y las cantidades, enteros en unidad base (INV-04).
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

/** Estado de envío de una venta local (D13): `PENDIENTE` («Sin enviar») hasta el resultado del servidor (22b). */
export type EstadoDeEnvio = 'PENDIENTE' | 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA'

export type ContenidoDeVentaLocal = Esquema['VentaConfirmarRequest']

export type SobreEnCola = Esquema['ItemLoteComandoRequest']

/** Importes ya calculados de una línea (strings de dos decimales, INV-03). */
export interface LineaCalculadaLocal {
  linea_id: string
  bruto: string
  descuentos: { origen: 'AUTOMATICO' | 'MANUAL'; regla_id: string | null; porcentaje: string | null; importe: string }[]
  descuento_total: string
  neto: string
  alicuota: string
  importe_iva: string
}

/**
 * Datos congelados de la nota al confirmar (D15, VTA-13): lo que no está en el contenido enviado
 * ni en el cálculo (nombres, organización, saldo resultante). La nota se arma siempre desde acá,
 * aunque un bootstrap posterior cambie los maestros.
 */
export interface NotaCongelada {
  organizacion: { nombre: string; cuit: string | null; domicilio: string | null; telefono: string | null }
  zona_horaria: string
  muestra_saldo: boolean
  modo_impositivo: 'A' | 'B' | 'C'
  vendedor_nombre: string
  cliente: {
    nombre: string
    razon_social: string | null
    documento_tipo: string | null
    documento_numero: string | null
    direccion: string | null
    es_consumidor_final: boolean
  }
  lineas: {
    linea_id: string
    producto_nombre: string
    presentacion_nombre: string | null
    unidades_presentacion: number
  }[]
  medios: { medio_pago_id: string; nombre: string }[]
  /** Saldo + total - cobrado (CRE-02); nulo para el consumidor final. */
  saldo_resultante: string | null
}

/**
 * Venta confirmada en el teléfono (D3): el contenido enviado, el resultado del cálculo local y
 * los datos congelados de la nota (D15, los completa el Lote 4).
 */
export interface VentaLocal {
  venta_id: string
  operation_id: string
  numero: string
  cliente_id: string
  jornada_id: string
  occurred_at: string
  estado_envio: EstadoDeEnvio
  contenido: ContenidoDeVentaLocal
  calculo: {
    lineas: LineaCalculadaLocal[]
    total_neto: string
    total_iva: string
    total: string
  }
  nota: NotaCongelada | null
}

export interface CobranzaLocal {
  cobranza_id: string
  venta_id: string
  operation_id: string
  jornada_id: string
  medios: { medio_pago_id: string; importe: string; referencia: string | null }[]
  total: string
}

export type TipoDeMovimientoLocal = 'VENTA_STOCK' | 'VENTA_DEBITO' | 'COBRANZA_CREDITO'

/**
 * Efecto local de una operación sobre stock o cuenta (D5). `VENTA_STOCK` guarda `cantidad_base`
 * entera y NEGATIVA (sale mercadería); `VENTA_DEBITO` y `COBRANZA_CREDITO` guardan `importe`
 * positivo como string: el tipo dice el sentido.
 */
export interface MovimientoLocal {
  id?: number
  operation_id: string
  jornada_id: string
  tipo: TipoDeMovimientoLocal
  producto_id: string | null
  cliente_id: string | null
  cantidad_base: number | null
  importe: string | null
  /** `PENDIENTE` hasta la conciliación con un bootstrap posterior (la escribe el change 22c; el 22b NO la cambia, D4). */
  estado_operacion: 'PENDIENTE' | 'RESUELTA'
}

/**
 * Estado de un comando de la cola (change 22b, `design.md` D3): `PENDIENTE` hasta que el servidor
 * responde; después toma el estado del resultado. Nunca se borra (SYN-09). Sin versión nueva de
 * Dexie: el índice `estado` ya existe.
 */
export type EstadoDeComando = 'PENDIENTE' | 'ACEPTADO' | 'ACEPTADO_CON_OBSERVACIONES' | 'RECHAZADO'

export interface ComandoEnCola {
  secuencia: number
  operation_id: string
  estado: EstadoDeComando
  sobre: SobreEnCola
  /** Código del rechazo del servidor (solo con `RECHAZADO`). */
  error_codigo?: string | null
  /** Momento local (ISO) en que se escribió el resultado. */
  resultado_en?: string
}

/** Fallos del PIN de un supervisor por par (usuario, autorizador); no guarda horas (D10). */
export interface IntentoPinLocal {
  usuario_id: string
  autorizador_id: string
  fallos: number
  derivacion: string
  bloqueado: boolean
}

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
  ventas!: EntityTable<VentaLocal, 'venta_id'>
  cobranzas!: EntityTable<CobranzaLocal, 'cobranza_id'>
  movimientos_locales!: EntityTable<MovimientoLocal, 'id'>
  cola!: EntityTable<ComandoEnCola, 'secuencia'>
  intentos_pin!: Table<IntentoPinLocal, [string, string]>

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
    this.version(3).stores({
      ventas: 'venta_id, operation_id, jornada_id, estado_envio, numero',
      cobranzas: 'cobranza_id, venta_id',
      movimientos_locales: '++id, operation_id, [jornada_id+producto_id], [jornada_id+cliente_id]',
      cola: 'secuencia, &operation_id, estado',
      intentos_pin: '[usuario_id+autorizador_id]',
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
