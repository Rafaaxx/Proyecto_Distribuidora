import type { ResultadoVenta } from '../calculo'
import type {
  CobranzaLocal,
  ContenidoDeVentaLocal,
  LineaCalculadaLocal,
  MovimientoLocal,
  NotaCongelada,
  VentaLocal,
} from '../../lib/dispositivo/db'
import { redondearImporte, type Importe } from '../../lib/money'

/**
 * De una venta calculada a las filas locales (change 22a, `design.md` D3, D5; VTA-12, RUT-04,
 * CRE-08, INV-03, INV-04). Función pura: no escribe nada (la transacción es de
 * `sync/confirmarVentaLocal.ts`). Todas las filas comparten el `operation_id`; los importes son
 * string de dos decimales y las cantidades, enteros en unidad base.
 */
export interface LineaBaseDeVenta {
  lineaId: string
  productoId: string
  /** Cantidad en unidad base (INV-04). */
  cantidadBase: number
}

export interface EntradaVentaLocal {
  /** El contenido del comando (`VentaConfirmarRequest`, sin credenciales). */
  contenido: ContenidoDeVentaLocal
  calculo: ResultadoVenta
  lineas: readonly LineaBaseDeVenta[]
  jornadaId: string
  operationId: string
  /** ISO UTC del momento de confirmar. */
  occurredAt: string
  /** Datos congelados de la nota (D15); los completa el Lote 4. */
  nota: NotaCongelada | null
}

export interface OperacionesLocales {
  venta: VentaLocal
  cobranza: CobranzaLocal | null
  movimientos: MovimientoLocal[]
}

function lineaCalculada(l: ResultadoVenta['lineas'][number]): LineaCalculadaLocal {
  return {
    linea_id: l.id,
    bruto: l.bruto.toFixed(2),
    descuentos: l.descuentos.map((d) => ({
      origen: d.origen,
      regla_id: d.reglaId,
      porcentaje: d.porcentaje === null ? null : d.porcentaje.toFixed(6),
      importe: d.importe.toFixed(2),
    })),
    descuento_total: l.descuentoTotal.toFixed(2),
    neto: l.neto.toFixed(2),
    alicuota: l.alicuota.toFixed(6),
    importe_iva: l.importeIva.toFixed(2),
  }
}

export function derivarOperacionesLocales(entrada: EntradaVentaLocal): OperacionesLocales {
  const { contenido, calculo, operationId, jornadaId } = entrada
  const enContenido = contenido.cobranza ?? null

  const venta: VentaLocal = {
    venta_id: contenido.venta_id,
    operation_id: operationId,
    numero: contenido.numero,
    cliente_id: contenido.cliente_id,
    jornada_id: jornadaId,
    occurred_at: entrada.occurredAt,
    estado_envio: 'PENDIENTE',
    contenido,
    calculo: {
      lineas: calculo.lineas.map(lineaCalculada),
      total_neto: calculo.totalNeto.toFixed(2),
      total_iva: calculo.totalIva.toFixed(2),
      total: calculo.total.toFixed(2),
    },
    nota: entrada.nota,
  }

  let cobrado: Importe = redondearImporte('0')
  let cobranza: CobranzaLocal | null = null
  if (enContenido !== null) {
    for (const medio of enContenido.medios) cobrado = cobrado.plus(redondearImporte(medio.importe))
    cobranza = {
      cobranza_id: enContenido.cobranza_id,
      venta_id: contenido.venta_id,
      operation_id: operationId,
      jornada_id: jornadaId,
      medios: enContenido.medios.map((m) => ({
        medio_pago_id: m.medio_pago_id,
        importe: redondearImporte(m.importe).toFixed(2),
        referencia: m.referencia ?? null,
      })),
      total: cobrado.toFixed(2),
    }
  }

  const base = { operation_id: operationId, jornada_id: jornadaId, estado_operacion: 'PENDIENTE' } as const
  const movimientos: MovimientoLocal[] = entrada.lineas.map((l) => ({
    ...base,
    tipo: 'VENTA_STOCK',
    producto_id: l.productoId,
    cliente_id: null,
    cantidad_base: -l.cantidadBase,
    importe: null,
  }))
  movimientos.push({
    ...base,
    tipo: 'VENTA_DEBITO',
    producto_id: null,
    cliente_id: contenido.cliente_id,
    cantidad_base: null,
    importe: calculo.total.toFixed(2),
  })
  if (cobranza !== null && cobrado.greaterThan(0)) {
    movimientos.push({
      ...base,
      tipo: 'COBRANZA_CREDITO',
      producto_id: null,
      cliente_id: contenido.cliente_id,
      cantidad_base: null,
      importe: cobrado.toFixed(2),
    })
  }

  return { venta, cobranza, movimientos }
}
