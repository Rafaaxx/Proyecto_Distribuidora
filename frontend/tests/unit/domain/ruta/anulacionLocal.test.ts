/**
 * Change 22d, tarea 6.1 (spec `sync/cola-local`, «Anular una venta local es una sola transacción»
 * y «La anulación local cuenta en el saldo y el stock locales»; `design.md` D5, D6; VTA-21,
 * VTA-22, INV-19, INV-03, INV-04): de la venta local, su cobro y la devolución a la anulación y
 * sus movimientos inversos.
 */
import { describe, expect, it } from 'vitest'

import {
  derivarAnulacionLocal,
  ErrorDeAnulacionLocal,
  type EntradaDeAnulacionLocal,
} from '../../../../src/domain/ruta/anulacionLocal'
import { saldoConsiderado, stockDisponible } from '../../../../src/domain/ruta/disponiblesLocales'
import type { CobranzaLocal, MovimientoLocal, VentaLocal } from '../../../../src/lib/dispositivo/db'

const JORNADA = 'jornada-1'
const CLIENTE = 'cliente-1'
const VINO = 'producto-vino'
const GASEOSA = 'producto-gaseosa'

function ventaDePrueba(total = '70000.00'): VentaLocal {
  return {
    venta_id: 'venta-7',
    operation_id: 'op-venta-7',
    numero: 'V03-000142',
    cliente_id: CLIENTE,
    jornada_id: JORNADA,
    occurred_at: '2026-11-03T10:00:00.000Z',
    estado_envio: 'PENDIENTE',
    contenido: {} as never,
    calculo: { lineas: [], total_neto: total, total_iva: '0.00', total },
    nota: null,
  }
}

function cobranzaDePrueba(total: string): CobranzaLocal {
  return {
    cobranza_id: 'cobranza-7',
    venta_id: 'venta-7',
    operation_id: 'op-venta-7',
    jornada_id: JORNADA,
    medios: [{ medio_pago_id: 'efectivo', importe: total, referencia: null }],
    total,
  }
}

function movimientosDeVenta(total = '70000.00', cobrado: string | null = '20000.00'): MovimientoLocal[] {
  const base = { operation_id: 'op-venta-7', jornada_id: JORNADA, estado_operacion: 'PENDIENTE' } as const
  const lista: MovimientoLocal[] = [
    { ...base, tipo: 'VENTA_STOCK', producto_id: VINO, cliente_id: null, cantidad_base: -15, importe: null },
    { ...base, tipo: 'VENTA_STOCK', producto_id: GASEOSA, cliente_id: null, cantidad_base: -4, importe: null },
    { ...base, tipo: 'VENTA_DEBITO', producto_id: null, cliente_id: CLIENTE, cantidad_base: null, importe: total },
  ]
  if (cobrado !== null) {
    lista.push({
      ...base,
      tipo: 'COBRANZA_CREDITO',
      producto_id: null,
      cliente_id: CLIENTE,
      cantidad_base: null,
      importe: cobrado,
    })
  }
  return lista
}

function entrada(cambios: Partial<EntradaDeAnulacionLocal> = {}): EntradaDeAnulacionLocal {
  return {
    venta: ventaDePrueba(),
    cobranza: cobranzaDePrueba('20000.00'),
    movimientosDeVenta: movimientosDeVenta(),
    esConsumidorFinal: false,
    motivo: { id: 'motivo-1', nombre: 'Error de carga' },
    observacion: null,
    devuelveDinero: true,
    operationId: 'op-anul-7',
    occurredAt: '2026-11-03T12:30:00.000Z',
    ...cambios,
  }
}

function codigoDelError(f: () => unknown): string | undefined {
  try {
    f()
  } catch (e) {
    return e instanceof ErrorDeAnulacionLocal ? e.codigo : undefined
  }
  return undefined
}

describe('derivarAnulacionLocal: anulación y movimientos inversos', () => {
  it('con devolución: ingreso por línea en unidad base, crédito del total y débito de lo cobrado (VTA-22)', () => {
    const { anulacion, movimientos } = derivarAnulacionLocal(entrada())

    expect(anulacion).toEqual({
      venta_id: 'venta-7',
      operation_id: 'op-anul-7',
      jornada_id: JORNADA,
      estado_envio: 'PENDIENTE',
      motivo_id: 'motivo-1',
      motivo_nombre: 'Error de carga',
      observacion: null,
      devuelve_dinero: true,
      occurred_at: '2026-11-03T12:30:00.000Z',
    })
    const base = { operation_id: 'op-anul-7', jornada_id: JORNADA, estado_operacion: 'PENDIENTE' }
    expect(movimientos).toEqual([
      { ...base, tipo: 'ANULACION_STOCK', producto_id: VINO, cliente_id: null, cantidad_base: 15, importe: null },
      { ...base, tipo: 'ANULACION_STOCK', producto_id: GASEOSA, cliente_id: null, cantidad_base: 4, importe: null },
      { ...base, tipo: 'ANULACION_CREDITO', producto_id: null, cliente_id: CLIENTE, cantidad_base: null, importe: '70000.00' },
      {
        ...base,
        tipo: 'ANULACION_COBRANZA_DEBITO',
        producto_id: null,
        cliente_id: CLIENTE,
        cantidad_base: null,
        importe: '20000.00',
      },
    ])
  })

  it('sin devolución: no hay débito de lo cobrado (queda a favor del cliente)', () => {
    const { anulacion, movimientos } = derivarAnulacionLocal(entrada({ devuelveDinero: false }))

    expect(anulacion.devuelve_dinero).toBe(false)
    expect(movimientos.map((m) => m.tipo)).toEqual(['ANULACION_STOCK', 'ANULACION_STOCK', 'ANULACION_CREDITO'])
  })

  it('sin cobro en el acto: no se pregunta la devolución y no hay débito; devuelve_dinero queda null', () => {
    const { anulacion, movimientos } = derivarAnulacionLocal(
      entrada({ cobranza: null, movimientosDeVenta: movimientosDeVenta('70000.00', null), devuelveDinero: null }),
    )

    expect(anulacion.devuelve_dinero).toBeNull()
    expect(movimientos.map((m) => m.tipo)).toEqual(['ANULACION_STOCK', 'ANULACION_STOCK', 'ANULACION_CREDITO'])
  })

  it('una cobranza de importe cero cuenta como sin cobro', () => {
    const { anulacion } = derivarAnulacionLocal(
      entrada({
        cobranza: cobranzaDePrueba('0.00'),
        movimientosDeVenta: movimientosDeVenta('70000.00', null),
        devuelveDinero: null,
      }),
    )
    expect(anulacion.devuelve_dinero).toBeNull()
  })

  it('el consumidor final siempre devuelve, aunque se pida otra cosa (VTA-22)', () => {
    const { anulacion, movimientos } = derivarAnulacionLocal(entrada({ esConsumidorFinal: true, devuelveDinero: false }))

    expect(anulacion.devuelve_dinero).toBe(true)
    expect(movimientos.map((m) => m.tipo)).toContain('ANULACION_COBRANZA_DEBITO')
  })

  it('con cobro y sin elegir la devolución (cliente con cuenta) lanza DEVOLUCION_REQUERIDA', () => {
    expect(codigoDelError(() => derivarAnulacionLocal(entrada({ devuelveDinero: null })))).toBe('DEVOLUCION_REQUERIDA')
  })

  it('sin motivo lanza MOTIVO_REQUERIDO', () => {
    expect(codigoDelError(() => derivarAnulacionLocal(entrada({ motivo: { id: '', nombre: '' } })))).toBe(
      'MOTIVO_REQUERIDO',
    )
  })

  it('la observación se recorta; vacía es null; de más de 500 caracteres se rechaza (VTA-20)', () => {
    expect(derivarAnulacionLocal(entrada({ observacion: '  no recibió  ' })).anulacion.observacion).toBe('no recibió')
    expect(derivarAnulacionLocal(entrada({ observacion: '   ' })).anulacion.observacion).toBeNull()
    expect(derivarAnulacionLocal(entrada({ observacion: 'a'.repeat(500) })).anulacion.observacion).toHaveLength(500)
    expect(codigoDelError(() => derivarAnulacionLocal(entrada({ observacion: 'a'.repeat(501) })))).toBe(
      'OBSERVACION_INVALIDA',
    )
  })

  it('no toca los movimientos de la venta que recibe (función pura)', () => {
    const originales = movimientosDeVenta()
    const copia = JSON.parse(JSON.stringify(originales)) as MovimientoLocal[]
    derivarAnulacionLocal(entrada({ movimientosDeVenta: originales }))
    expect(originales).toEqual(copia)
  })
})

describe('los movimientos inversos devuelven el stock y la cuenta a como estaban (INV-19)', () => {
  it('con devolución: el stock y el saldo quedan como antes de la venta', () => {
    const { movimientos } = derivarAnulacionLocal(entrada())
    const todos = [...movimientosDeVenta(), ...movimientos]

    expect(stockDisponible(63, todos, VINO, JORNADA)).toBe(63)
    expect(stockDisponible(10, todos, GASEOSA, JORNADA)).toBe(10)
    expect(saldoConsiderado('100000.00', todos, CLIENTE, JORNADA)).toBe('100000.00')
  })

  it('sin devolución: el saldo difiere solo en lo cobrado (queda a favor)', () => {
    const { movimientos } = derivarAnulacionLocal(entrada({ devuelveDinero: false }))
    const todos = [...movimientosDeVenta(), ...movimientos]

    expect(stockDisponible(63, todos, VINO, JORNADA)).toBe(63)
    expect(saldoConsiderado('100000.00', todos, CLIENTE, JORNADA)).toBe('80000.00')
  })
})
