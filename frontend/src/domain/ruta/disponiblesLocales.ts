import type { MovimientoLocal } from '../../lib/dispositivo/db'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'

/**
 * Saldo y stock locales de la jornada (change 22a, `design.md` D5; CRE-08, COB-04, RUT-04,
 * STK-04, INV-03, INV-04). Funciones puras: reciben los movimientos locales ya leídos de Dexie.
 * Solo cuentan los de la jornada del bootstrap cuya operación no tiene resultado del servidor
 * (`PENDIENTE`); las de otra jornada y las resueltas no (el 22c decide cómo no contar dos veces
 * lo ya aceptado cuando llega un bootstrap posterior).
 */
function cuenta(m: MovimientoLocal, jornadaId: string): boolean {
  return m.jornada_id === jornadaId && m.estado_operacion === 'PENDIENTE'
}

/** CRE-08: saldo del bootstrap + débitos de venta - cobranzas locales. String de dos decimales. */
export function saldoConsiderado(
  saldoBootstrap: string,
  movimientos: readonly MovimientoLocal[],
  clienteId: string,
  jornadaId: string,
): string {
  let saldo = parsearImporteDesdeApi(saldoBootstrap)
  for (const m of movimientos) {
    if (!cuenta(m, jornadaId) || m.cliente_id !== clienteId || m.importe === null) continue
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
): number {
  let stock = stockBootstrap
  for (const m of movimientos) {
    if (!cuenta(m, jornadaId) || m.tipo !== 'VENTA_STOCK') continue
    if (m.producto_id !== productoId || m.cantidad_base === null) continue
    stock += m.cantidad_base
  }
  return stock
}
