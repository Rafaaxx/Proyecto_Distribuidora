/**
 * Tipos de entrada y salida del motor de descuentos (`design.md` D4, D11 del change 16).
 * Espejo de `backend/app/modules/descuentos/domain/tipos.py`.
 *
 * Los importes y porcentajes de entrada son cadenas decimales exactas (como llegan de la API,
 * `02` §10.2); nunca `number` (INV-03). El resultado trae `Importe` (decimal.js).
 */

import type { Importe } from '../../lib/money'

export type TipoRegla = 'VOLUMEN_OPERACION' | 'VOLUMEN_ALCANCE'
export type Medida = 'CAJAS_EQUIVALENTES' | 'UNIDADES_BASE' | 'IMPORTE_BRUTO'
export type Operador = 'GTE' | 'GT'
export type AccionTipo = 'PORCENTAJE' | 'IMPORTE_FIJO'
export type TipoAlcance = 'PRODUCTO' | 'CATEGORIA' | 'MARCA'
export type Origen = 'AUTOMATICO' | 'MANUAL'

export const TIPOS_REGLA: readonly string[] = ['VOLUMEN_OPERACION', 'VOLUMEN_ALCANCE']
export const MEDIDAS: readonly string[] = ['CAJAS_EQUIVALENTES', 'UNIDADES_BASE', 'IMPORTE_BRUTO']
export const OPERADORES: readonly string[] = ['GTE', 'GT']
export const ACCIONES: readonly string[] = ['PORCENTAJE', 'IMPORTE_FIJO']
export const TIPOS_ALCANCE: readonly string[] = ['PRODUCTO', 'CATEGORIA', 'MARCA']

/** Una línea de la venta: el bruto ya calculado por PRC-22 y sus unidades de referencia (D5). */
export interface LineaVenta {
  id: string
  bruto: string
  cantidadBase: number
  unidadesReferencia: number
  productoId: string
  categoriaId: string
  marcaId: string
  /** Porcentaje manual propio de la línea (fracción como cadena) o `null` (D11). */
  descuentoManual: string | null
}

export interface AlcanceRegla {
  tipo: TipoAlcance
  entidadId: string
}

/** Una regla aplicable (activa y vigente). El `id` es un UUIDv7: su orden es el de creación. */
export interface ReglaDescuento {
  id: string
  tipo: TipoRegla
  medida: Medida
  operador: Operador
  umbral: string
  accionTipo: AccionTipo
  accionPorcentaje: string | null
  accionImporte: string | null
  acumulable: boolean
  prioridad: number
  alcances: readonly AlcanceRegla[]
}

/** Un descuento de una línea (DSC-08). `reglaId` es nulo en el manual; `porcentaje`, en el importe fijo. */
export interface DescuentoAplicado {
  origen: Origen
  reglaId: string | null
  porcentaje: Importe | null
  importe: Importe
}

export interface LineaResultado {
  id: string
  descuentos: readonly DescuentoAplicado[]
  descuentoTotal: Importe
  neto: Importe
}

/**
 * Resultado por línea y el mayor porcentaje manual que quedó aplicado en alguna línea (nulo si
 * ninguna lleva manual): lo que se compara contra el tope (DSC-06; D11, D12).
 */
export interface ResultadoDescuentos {
  lineas: readonly LineaResultado[]
  porcentajeManualMaximo: Importe | null
}
