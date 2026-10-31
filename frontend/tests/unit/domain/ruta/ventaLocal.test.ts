import { describe, expect, it } from 'vitest'

import { calcularVenta, type LineaCalculo } from '../../../../src/domain/calculo'
import { derivarOperacionesLocales, type EntradaVentaLocal } from '../../../../src/domain/ruta/ventaLocal'
import type { ContenidoDeVentaLocal } from '../../../../src/lib/dispositivo/db'

/**
 * Change 22a, tarea 2.2 (`design.md` D3, D5; VTA-12, RUT-04, CRE-08, INV-03, INV-04): de una venta
 * calculada con `calcularVenta` se derivan la fila `VentaLocal`, la `CobranzaLocal` y los
 * movimientos locales, todos con el mismo `operation_id`.
 */
const OP = 'op-1'
const JORNADA = 'jor-1'

function linea(id: string, cantidadBase: number): LineaCalculo {
  return {
    id,
    precioReferencia: '12500.00',
    unidadesReferencia: 6,
    cantidadBase,
    alicuota: '0.210000',
    productoId: 'vino-a',
    categoriaId: 'vinos',
    marcaId: 'marca',
    descuentoManual: null,
  }
}

function entrada(opciones: { cobro?: { medio: string; importe: string; referencia: string | null }[] } = {}): EntradaVentaLocal {
  const lineas = [linea('l-1', 12), linea('l-2', 3)]
  const calculo = calcularVenta('A', lineas, [], null)
  const cobro = opciones.cobro ?? []
  const contenido = {
    venta_id: 'venta-1',
    numero: 'V03-000142',
    cliente_id: 'cli-1',
    lineas: [],
    total: calculo.total.toFixed(2),
    cobranza:
      cobro.length === 0
        ? null
        : {
            cobranza_id: 'cob-1',
            medios: cobro.map((m) => ({ medio_pago_id: m.medio, importe: m.importe, referencia: m.referencia })),
          },
  } as unknown as ContenidoDeVentaLocal
  return {
    contenido,
    calculo,
    lineas: [
      { lineaId: 'l-1', productoId: 'vino-a', cantidadBase: 12 },
      { lineaId: 'l-2', productoId: 'vino-a', cantidadBase: 3 },
    ],
    jornadaId: JORNADA,
    operationId: OP,
    occurredAt: '2026-10-19T12:00:00.000Z',
    nota: null,
  }
}

describe('operaciones locales derivadas de una venta (VTA-12, RUT-04, CRE-08)', () => {
  it('con cobranza: venta, cobranza y tres movimientos con el mismo operation_id', () => {
    const { venta, cobranza, movimientos } = derivarOperacionesLocales(
      entrada({ cobro: [{ medio: 'efectivo', importe: '20000.00', referencia: null }] }),
    )

    expect(venta).toMatchObject({
      venta_id: 'venta-1',
      operation_id: OP,
      numero: 'V03-000142',
      cliente_id: 'cli-1',
      jornada_id: JORNADA,
      estado_envio: 'PENDIENTE',
    })
    expect(venta.calculo.total).toBe('31250.00')
    expect(venta.calculo.lineas.map((l) => [l.linea_id, l.bruto, l.neto])).toEqual([
      ['l-1', '25000.00', '25000.00'],
      ['l-2', '6250.00', '6250.00'],
    ])
    expect(cobranza).toMatchObject({ cobranza_id: 'cob-1', venta_id: 'venta-1', operation_id: OP, total: '20000.00' })

    const porTipo = (tipo: string) => movimientos.filter((m) => m.tipo === tipo)
    expect(porTipo('VENTA_STOCK').map((m) => [m.producto_id, m.cantidad_base])).toEqual([
      ['vino-a', -12],
      ['vino-a', -3],
    ])
    expect(porTipo('VENTA_DEBITO')).toMatchObject([{ cliente_id: 'cli-1', importe: '31250.00', cantidad_base: null }])
    expect(porTipo('COBRANZA_CREDITO')).toMatchObject([{ cliente_id: 'cli-1', importe: '20000.00' }])
    expect(movimientos.every((m) => m.operation_id === OP && m.jornada_id === JORNADA && m.estado_operacion === 'PENDIENTE')).toBe(true)
  })

  it('sin cobranza: no hay cobranza ni crédito, solo stock y débito', () => {
    const { cobranza, movimientos } = derivarOperacionesLocales(entrada())

    expect(cobranza).toBeNull()
    expect(movimientos.map((m) => m.tipo)).toEqual(['VENTA_STOCK', 'VENTA_STOCK', 'VENTA_DEBITO'])
  })

  it('dos medios suman la cobranza en el crédito; importes string y cantidades enteras (INV-03, INV-04)', () => {
    const { cobranza, movimientos } = derivarOperacionesLocales(
      entrada({
        cobro: [
          { medio: 'efectivo', importe: '10000.10', referencia: null },
          { medio: 'transf', importe: '9999.95', referencia: 'REF-1' },
        ],
      }),
    )

    expect(cobranza?.total).toBe('20000.05')
    expect(cobranza?.medios).toEqual([
      { medio_pago_id: 'efectivo', importe: '10000.10', referencia: null },
      { medio_pago_id: 'transf', importe: '9999.95', referencia: 'REF-1' },
    ])
    expect(movimientos.find((m) => m.tipo === 'COBRANZA_CREDITO')?.importe).toBe('20000.05')
    for (const m of movimientos) {
      if (m.importe !== null) expect(m.importe).toMatch(/^\d+\.\d{2}$/)
      if (m.cantidad_base !== null) expect(Number.isInteger(m.cantidad_base)).toBe(true)
    }
  })
})
