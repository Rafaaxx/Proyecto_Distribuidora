import type { components } from '../../api/schema.gen'
import { calcularEgreso, calcularIngreso, validarCosto } from '../costeo/costoPromedio'
import { aUnidadesBase } from './cantidades'

/**
 * Stock inicial (change 09, tarea 8.4; `design.md` D4, D5, D6, D14, D15): una
 * línea se escribe en cajas + unidades, se convierte a unidad base entera y el
 * costo viaja como string (solo en un ingreso; una corrección egresa al promedio
 * vigente y no lleva costo). Lógica pura, sin React. El servidor valida y
 * recalcula siempre (TR-10): esto es UX y previsualización.
 */

export type CuerpoStockInicial = components['schemas']['StockInicialRegistrarRequest']
type LineaDeCuerpo = components['schemas']['LineaStockInicialRequest']

export type SentidoDeLinea = 'INGRESO' | 'CORRECCION'

/** Una línea tal como la escribe el usuario: todo texto. */
export interface LineaDeFormulario {
  productoId: string
  sentido: SentidoDeLinea
  cajas: string
  unidades: string
  costo: string
}

export type ResultadoDeLinea = { ok: true; payload: LineaDeCuerpo } | { ok: false; mensaje: string }

export const MAXIMO_DE_LINEAS = 200

const ENTERO_TEXTO = /^\d+$/

export function parteEntera(texto: string, nombre: string): number | string {
  const limpio = texto.trim()
  if (limpio === '') return 0
  if (!ENTERO_TEXTO.test(limpio)) return `${nombre}: ingresá un entero mayor o igual a cero.`
  return Number(limpio)
}

/**
 * Convierte y valida una línea. `unidadesPorCaja` es el de la presentación de
 * referencia del producto (`null` si no tiene: solo unidades) y
 * `nombrePresentacion` su nombre, que rotula la parte en presentaciones en los
 * mensajes (sin nombre, "Cajas").
 */
export function validarLinea(
  linea: LineaDeFormulario,
  unidadesPorCaja: number | null,
  nombrePresentacion: string | null = null,
): ResultadoDeLinea {
  if (linea.productoId === '') return { ok: false, mensaje: 'Elegí un producto.' }

  const cajas = parteEntera(linea.cajas, nombrePresentacion ?? 'Cajas')
  if (typeof cajas === 'string') return { ok: false, mensaje: cajas }
  const unidades = parteEntera(linea.unidades, 'Unidades')
  if (typeof unidades === 'string') return { ok: false, mensaje: unidades }

  let magnitud: number
  try {
    magnitud = aUnidadesBase(cajas, unidades, unidadesPorCaja)
  } catch (error) {
    return { ok: false, mensaje: error instanceof Error ? error.message : 'La cantidad no es válida.' }
  }
  if (magnitud === 0) return { ok: false, mensaje: 'La cantidad tiene que ser mayor que cero.' }

  if (linea.sentido === 'CORRECCION') {
    return { ok: true, payload: { producto_id: linea.productoId, cantidad_base: -magnitud } }
  }

  const costo = linea.costo.trim()
  try {
    validarCosto(costo)
  } catch {
    return {
      ok: false,
      mensaje: 'Ingresá un costo mayor a cero, con punto decimal y hasta seis decimales.',
    }
  }
  return { ok: true, payload: { producto_id: linea.productoId, cantidad_base: magnitud, costo_unitario: costo } }
}

export type ResultadoDeEnvio =
  | { ok: true; cuerpo: CuerpoStockInicial }
  | { ok: false; mensaje: string; indice?: number }

/** Valida todas las líneas (1 a 200, sin producto repetido, D5) y arma el cuerpo. */
export function armarEnvio(
  ubicacionId: string,
  lineas: { linea: LineaDeFormulario; unidadesPorCaja: number | null; nombrePresentacion?: string | null }[],
): ResultadoDeEnvio {
  if (lineas.length === 0) return { ok: false, mensaje: 'Agregá al menos una línea.' }
  if (lineas.length > MAXIMO_DE_LINEAS) {
    return { ok: false, mensaje: `Un envío admite hasta ${String(MAXIMO_DE_LINEAS)} líneas.` }
  }

  const vistos = new Set<string>()
  const payloads: LineaDeCuerpo[] = []
  for (const [indice, { linea, unidadesPorCaja, nombrePresentacion }] of lineas.entries()) {
    const resultado = validarLinea(linea, unidadesPorCaja, nombrePresentacion ?? null)
    if (!resultado.ok) return { ok: false, mensaje: resultado.mensaje, indice }
    if (vistos.has(linea.productoId)) {
      return { ok: false, mensaje: 'Un producto no puede repetirse en el mismo envío.', indice }
    }
    vistos.add(linea.productoId)
    payloads.push(resultado.payload)
  }
  return { ok: true, cuerpo: { ubicacion_id: ubicacionId, lineas: payloads } }
}

export interface EntradaDePrevisualizacion {
  stockTotal: number
  /** Promedio vigente (string de la API) o `null` si el producto nunca tuvo ingresos (D10). */
  promedio: string | null
  /** Con signo: positiva es un ingreso, negativa una corrección. */
  cantidadBase: number
  /** Costo del ingreso; `null` en una corrección. */
  costo: string | null
}

/**
 * Promedio resultante (string con seis decimales) con la misma función que los
 * fixtures de CST-11 (D14), o `null` si no se puede calcular (costo inválido o
 * faltante, cantidad cero). No reemplaza al servidor (TR-10).
 */
export function previsualizarPromedio(entrada: EntradaDePrevisualizacion): string | null {
  try {
    if (entrada.cantidadBase > 0) {
      if (entrada.costo === null) return null
      const { promedioNuevo } = calcularIngreso(entrada.stockTotal, entrada.promedio, entrada.cantidadBase, entrada.costo)
      return promedioNuevo.toFixed(6)
    }
    if (entrada.cantidadBase < 0) {
      const { promedioNuevo } = calcularEgreso(entrada.stockTotal, entrada.promedio, -entrada.cantidadBase)
      return promedioNuevo === null ? null : promedioNuevo.toFixed(6)
    }
    return null
  } catch {
    return null
  }
}

/** Un envío cortado por la red antes de recibir respuesta. */
export interface EnvioPendiente {
  cuerpo: CuerpoStockInicial
  operationId: string
}

/**
 * Elige el `operation_id` (INV-06, TR-07): si el usuario reintenta exactamente lo
 * que se cortó por la red, se reenvía el mismo y el servidor no duplica; si
 * cambió cualquier dato, es otra operación.
 */
export function resolverOperationId(
  pendiente: EnvioPendiente | null,
  cuerpo: CuerpoStockInicial,
  generar: () => string,
): string {
  if (pendiente && JSON.stringify(pendiente.cuerpo) === JSON.stringify(cuerpo)) {
    return pendiente.operationId
  }
  return generar()
}
