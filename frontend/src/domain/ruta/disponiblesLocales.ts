import type { MovimientoLocal } from '../../lib/dispositivo/db'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'

/**
 * Saldo y stock locales de la jornada (change 22a, `design.md` D5; change 22c, D1 y D2; CRE-08,
 * COB-04, RUT-04, STK-04, INV-03, INV-04, INV-06, SYN-06). Funciones puras: reciben los
 * movimientos locales ya leídos de Dexie y la conciliación.
 *
 * Un movimiento de la jornada del bootstrap cuenta si y solo si:
 * - su operación tiene una `secuencia` MAYOR que la marca `secuencia_procesada` del bootstrap
 *   (lo que el servidor todavía no tiene en la foto); o
 * - su operación está «Rechazada» (D2: sigue contando completa -stock, débito y cobro en el momento-
 *   hasta que termine la jornada); o
 * - no hay marca (bootstrap anterior al 22c: se cuenta todo, como hasta ahora); o
 * - no se conoce su operación (no hay evidencia de que el servidor la tenga).
 * `estado_operacion` del movimiento ya no se lee.
 */
export interface OperacionConciliable {
  /** Secuencia del comando en la cola. */
  secuencia: number
  /** El servidor rechazó la operación (estado `RECHAZADO` de la cola). */
  rechazada: boolean
}

export interface Conciliacion {
  /** Marca de la sesión local; `null` = el servidor no tenía ninguna (o no la informó). */
  secuenciaProcesada: number | null
  /** Por `operation_id`. */
  operaciones: ReadonlyMap<string, OperacionConciliable>
}

/** Sin conciliación todo lo de la jornada cuenta. */
export const SIN_CONCILIACION: Conciliacion = { secuenciaProcesada: null, operaciones: new Map() }

function cuenta(m: MovimientoLocal, jornadaId: string, conciliacion: Conciliacion): boolean {
  if (m.jornada_id !== jornadaId) return false
  const marca = conciliacion.secuenciaProcesada
  if (marca === null) return true
  const operacion = conciliacion.operaciones.get(m.operation_id)
  if (operacion === undefined) return true
  // D2 (precisión aprobada 2026-11-02): una operación rechazada cuenta COMPLETA (stock, débito y el
  // cobro en el momento, todos con su operation_id). La cobranza suelta sin conexión llega en el
  // change 23, que decidirá su propia regla.
  if (operacion.rechazada) return true
  return operacion.secuencia > marca
}

/** Los movimientos de la jornada que todavía cuentan sobre los valores del bootstrap. */
export function movimientosQueCuentan(
  movimientos: readonly MovimientoLocal[],
  jornadaId: string,
  conciliacion: Conciliacion = SIN_CONCILIACION,
): MovimientoLocal[] {
  return movimientos.filter((m) => cuenta(m, jornadaId, conciliacion))
}

/** CRE-08: saldo del bootstrap + débitos de venta - cobranzas locales. String de dos decimales. */
export function saldoConsiderado(
  saldoBootstrap: string,
  movimientos: readonly MovimientoLocal[],
  clienteId: string,
  jornadaId: string,
  conciliacion: Conciliacion = SIN_CONCILIACION,
): string {
  let saldo = parsearImporteDesdeApi(saldoBootstrap)
  for (const m of movimientos) {
    if (!cuenta(m, jornadaId, conciliacion) || m.cliente_id !== clienteId || m.importe === null) continue
    const importe = parsearImporteDesdeApi(m.importe)
    if (m.tipo === 'VENTA_DEBITO') saldo = saldo.plus(importe)
    else if (m.tipo === 'COBRANZA_CREDITO') saldo = saldo.minus(importe)
  }
  return redondearImporte(saldo).toFixed(2)
}

/** CRE-01: límite - saldo; `null` sin límite. */
export function creditoDisponibleLocal(limite: string | null, saldo: string): string | null {
  if (limite === null) return null
  return redondearImporte(parsearImporteDesdeApi(limite).minus(parsearImporteDesdeApi(saldo))).toFixed(2)
}

/** RUT-04: stock del bootstrap + movimientos de venta (cantidades negativas), en unidad base. */
export function stockDisponible(
  stockBootstrap: number,
  movimientos: readonly MovimientoLocal[],
  productoId: string,
  jornadaId: string,
  conciliacion: Conciliacion = SIN_CONCILIACION,
): number {
  let stock = stockBootstrap
  for (const m of movimientos) {
    if (!cuenta(m, jornadaId, conciliacion) || m.tipo !== 'VENTA_STOCK') continue
    if (m.producto_id !== productoId || m.cantidad_base === null) continue
    stock += m.cantidad_base
  }
  return stock
}

/**
 * RUT-04: disponible de todos los productos, para la pantalla de Stock. Incluye los que tienen
 * fila en el bootstrap y los que solo tienen movimientos (parten de cero).
 */
export function stockDeTodos(
  stockBootstrap: readonly { producto_id: string; cantidad_base: number }[],
  movimientos: readonly MovimientoLocal[],
  jornadaId: string,
  conciliacion: Conciliacion = SIN_CONCILIACION,
): Map<string, number> {
  const base = new Map<string, number>(stockBootstrap.map((f) => [f.producto_id, f.cantidad_base]))
  for (const m of movimientos) {
    if (m.tipo === 'VENTA_STOCK' && m.producto_id !== null && !base.has(m.producto_id)) base.set(m.producto_id, 0)
  }
  const resultado = new Map<string, number>()
  for (const [productoId, cantidad] of base) {
    resultado.set(productoId, stockDisponible(cantidad, movimientos, productoId, jornadaId, conciliacion))
  }
  return resultado
}
