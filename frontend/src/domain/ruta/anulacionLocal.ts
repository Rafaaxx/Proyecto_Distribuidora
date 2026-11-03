import type { AnulacionLocal, CobranzaLocal, MovimientoLocal, VentaLocal } from '../../lib/dispositivo/db'
import { redondearImporte } from '../../lib/money'

/**
 * De una venta local a su anulación y sus movimientos inversos (change 22d, `design.md` D5, D6;
 * VTA-20, VTA-21, VTA-22, VTA-24, INV-03, INV-04, INV-19). Función pura: no escribe nada (la
 * transacción es de `sync/anularVentaLocal.ts`).
 *
 * - `ANULACION_STOCK`: una por línea de la venta, la cantidad en unidad base (positiva: vuelve).
 * - `ANULACION_CREDITO`: el total de la venta, que se descuenta de la cuenta del cliente.
 * - `ANULACION_COBRANZA_DEBITO`: lo cobrado en el acto, solo si se devuelve el dinero.
 *
 * La devolución (VTA-22): sin cobro en el acto no se pregunta (`null`, el sobre la omite); con
 * cobro la elige el vendedor, salvo el consumidor final, que siempre devuelve. Todas las filas
 * llevan el `operation_id` de la anulación.
 */
export const LARGO_MAXIMO_DE_OBSERVACION = 500

export type CodigoDeErrorDeAnulacionLocal =
  | 'MOTIVO_REQUERIDO'
  | 'OBSERVACION_INVALIDA'
  | 'DEVOLUCION_REQUERIDA'
  /** La venta no está en el teléfono, es de otra jornada o está «Rechazada» (D5). */
  | 'VENTA_NO_ANULABLE'

export class ErrorDeAnulacionLocal extends Error {
  readonly codigo: CodigoDeErrorDeAnulacionLocal

  constructor(codigo: CodigoDeErrorDeAnulacionLocal, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeAnulacionLocal'
    this.codigo = codigo
  }
}

export interface EntradaDeAnulacionLocal {
  venta: VentaLocal
  /** Cobranza de la venta en el acto, si hubo. */
  cobranza: CobranzaLocal | null
  /** Los movimientos locales de la venta (se invierten los `VENTA_STOCK`). */
  movimientosDeVenta: readonly MovimientoLocal[]
  esConsumidorFinal: boolean
  motivo: { id: string; nombre: string }
  observacion: string | null
  /** Elección del vendedor; `null` si no se preguntó. */
  devuelveDinero: boolean | null
  /** UUIDv7 de la anulación (se reutiliza al reintentar). */
  operationId: string
  /** ISO UTC del momento de confirmar. */
  occurredAt: string
}

export interface OperacionesDeAnulacionLocal {
  anulacion: AnulacionLocal
  movimientos: MovimientoLocal[]
}

export function derivarAnulacionLocal(entrada: EntradaDeAnulacionLocal): OperacionesDeAnulacionLocal {
  const { venta, cobranza, motivo } = entrada
  if (motivo.id === '') throw new ErrorDeAnulacionLocal('MOTIVO_REQUERIDO', 'Falta el motivo de la anulación.')

  const observacionRecortada = entrada.observacion?.trim() ?? ''
  if (observacionRecortada.length > LARGO_MAXIMO_DE_OBSERVACION) {
    throw new ErrorDeAnulacionLocal(
      'OBSERVACION_INVALIDA',
      `La observación admite hasta ${LARGO_MAXIMO_DE_OBSERVACION} caracteres.`,
    )
  }

  const cobrado = redondearImporte(cobranza?.total ?? '0')
  const hayCobro = cobrado.greaterThan(0)
  let devuelveDinero: boolean | null = null
  if (hayCobro) {
    devuelveDinero = entrada.esConsumidorFinal ? true : entrada.devuelveDinero
    if (devuelveDinero === null) {
      throw new ErrorDeAnulacionLocal('DEVOLUCION_REQUERIDA', 'Hay que indicar si se devuelve lo cobrado.')
    }
  }

  const base = { operation_id: entrada.operationId, jornada_id: venta.jornada_id, estado_operacion: 'PENDIENTE' } as const
  const movimientos: MovimientoLocal[] = entrada.movimientosDeVenta
    .filter((m) => m.tipo === 'VENTA_STOCK' && m.cantidad_base !== null)
    .map((m) => ({
      ...base,
      tipo: 'ANULACION_STOCK',
      producto_id: m.producto_id,
      cliente_id: null,
      cantidad_base: -(m.cantidad_base as number),
      importe: null,
    }))
  movimientos.push({
    ...base,
    tipo: 'ANULACION_CREDITO',
    producto_id: null,
    cliente_id: venta.cliente_id,
    cantidad_base: null,
    importe: redondearImporte(venta.calculo.total).toFixed(2),
  })
  if (devuelveDinero === true) {
    movimientos.push({
      ...base,
      tipo: 'ANULACION_COBRANZA_DEBITO',
      producto_id: null,
      cliente_id: venta.cliente_id,
      cantidad_base: null,
      importe: cobrado.toFixed(2),
    })
  }

  const anulacion: AnulacionLocal = {
    venta_id: venta.venta_id,
    operation_id: entrada.operationId,
    jornada_id: venta.jornada_id,
    estado_envio: 'PENDIENTE',
    motivo_id: motivo.id,
    motivo_nombre: motivo.nombre,
    observacion: observacionRecortada === '' ? null : observacionRecortada,
    devuelve_dinero: devuelveDinero,
    occurred_at: entrada.occurredAt,
  }
  return { anulacion, movimientos }
}
