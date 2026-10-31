/**
 * Change 22a, tarea 5.1: saldo y stock locales (spec `sync/cola-local`, "El saldo y el stock
 * locales suman lo que hizo el teléfono"; D5; CRE-08, COB-04, RUT-04, STK-04, INV-03, INV-04).
 */
import { describe, expect, it } from 'vitest'

import {
  creditoDisponibleLocal,
  saldoConsiderado,
  stockDisponible,
} from '../../../../src/domain/ruta/disponiblesLocales'
import type { MovimientoLocal } from '../../../../src/lib/dispositivo/db'

const JORNADA = 'jornada-1'
const CLIENTE = 'cliente-1'
const VINO = 'producto-vino'

function mov(parcial: Partial<MovimientoLocal>): MovimientoLocal {
  return {
    operation_id: 'op-1',
    jornada_id: JORNADA,
    tipo: 'VENTA_DEBITO',
    producto_id: null,
    cliente_id: null,
    cantidad_base: null,
    importe: null,
    estado_operacion: 'PENDIENTE',
    ...parcial,
  }
}

const debito = (importe: string, extra: Partial<MovimientoLocal> = {}) =>
  mov({ tipo: 'VENTA_DEBITO', cliente_id: CLIENTE, importe, ...extra })
const credito = (importe: string, extra: Partial<MovimientoLocal> = {}) =>
  mov({ tipo: 'COBRANZA_CREDITO', cliente_id: CLIENTE, importe, ...extra })
const venta = (cantidad: number, extra: Partial<MovimientoLocal> = {}) =>
  mov({ tipo: 'VENTA_STOCK', producto_id: VINO, cantidad_base: -cantidad, ...extra })

describe('saldoConsiderado (CRE-08, COB-04)', () => {
  it('suma débitos y resta cobranzas: 100.000 + 70.000 - 20.000 = 150.000 y disponible 50.000', () => {
    const saldo = saldoConsiderado('100000.00', [debito('70000.00'), credito('20000.00')], CLIENTE, JORNADA)
    expect(saldo).toBe('150000.00')
    expect(creditoDisponibleLocal('200000.00', saldo)).toBe('50000.00')
  })

  it('sin movimientos es el saldo del bootstrap', () => {
    expect(saldoConsiderado('1234.50', [], CLIENTE, JORNADA)).toBe('1234.50')
  })

  it('no cuenta las operaciones de otra jornada (RUT-04)', () => {
    const saldo = saldoConsiderado(
      '100000.00',
      [debito('70000.00', { jornada_id: 'jornada-vieja' }), debito('1000.00')],
      CLIENTE,
      JORNADA,
    )
    expect(saldo).toBe('101000.00')
  })

  it('no cuenta las operaciones con resultado del servidor ni las de otro cliente', () => {
    const saldo = saldoConsiderado(
      '100000.00',
      [
        debito('70000.00', { estado_operacion: 'RESUELTA' }),
        debito('5000.00', { cliente_id: 'otro' }),
        debito('300.25'),
      ],
      CLIENTE,
      JORNADA,
    )
    expect(saldo).toBe('100300.25')
  })

  it('es exacto con centavos (INV-03)', () => {
    expect(saldoConsiderado('0.10', [debito('0.20')], CLIENTE, JORNADA)).toBe('0.30')
  })

  it('un saldo a favor sigue siendo negativo y sin límite no hay disponible', () => {
    expect(saldoConsiderado('-500.00', [debito('200.00')], CLIENTE, JORNADA)).toBe('-300.00')
    expect(creditoDisponibleLocal(null, '10.00')).toBeNull()
  })
})

describe('stockDisponible (RUT-04, STK-04)', () => {
  it('63 botellas del bootstrap menos una venta de 15 = 48', () => {
    expect(stockDisponible(63, [venta(15)], VINO, JORNADA)).toBe(48)
  })

  it('suma varias ventas y puede quedar negativo (INV-04: enteros)', () => {
    expect(stockDisponible(63, [venta(15), venta(50)], VINO, JORNADA)).toBe(-2)
  })

  it('ignora otra jornada, otro producto y operaciones resueltas', () => {
    const movimientos = [
      venta(10, { jornada_id: 'jornada-vieja' }),
      venta(7, { producto_id: 'otro' }),
      venta(5, { estado_operacion: 'RESUELTA' }),
      venta(3),
    ]
    expect(stockDisponible(63, movimientos, VINO, JORNADA)).toBe(60)
  })

  it('un producto sin stock en el bootstrap parte de cero', () => {
    expect(stockDisponible(0, [venta(4)], VINO, JORNADA)).toBe(-4)
  })
})
