/**
 * Change 22a, tarea 5.1: saldo y stock locales (spec `sync/cola-local`, "El saldo y el stock
 * locales suman lo que hizo el teléfono"; D5; CRE-08, COB-04, RUT-04, STK-04, INV-03, INV-04).
 */
import { describe, expect, it } from 'vitest'

import {
  creditoDisponibleLocal,
  movimientosQueCuentan,
  saldoConsiderado,
  SIN_CONCILIACION,
  stockDisponible,
  stockDeTodos,
  type Conciliacion,
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

  it('no cuenta las operaciones de otro cliente', () => {
    const saldo = saldoConsiderado(
      '100000.00',
      [debito('5000.00', { cliente_id: 'otro' }), debito('300.25')],
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

  it('ignora otra jornada y otro producto', () => {
    const movimientos = [venta(10, { jornada_id: 'jornada-vieja' }), venta(7, { producto_id: 'otro' }), venta(3)]
    expect(stockDisponible(63, movimientos, VINO, JORNADA)).toBe(60)
  })

  it('un producto sin stock en el bootstrap parte de cero', () => {
    expect(stockDisponible(0, [venta(4)], VINO, JORNADA)).toBe(-4)
  })
})

/**
 * Change 22c, tarea 7.1 (spec `sync/cola-local`, «El saldo y el stock locales suman lo que hizo el
 * teléfono»; D1, D2; CRE-08, RUT-04, COB-04, SYN-06, INV-06, INV-03, INV-04): conciliación por
 * secuencia procesada.
 */
function conciliacion(
  secuenciaProcesada: number | null,
  operaciones: Record<string, { secuencia: number; rechazada?: boolean }>,
): Conciliacion {
  return {
    secuenciaProcesada,
    operaciones: new Map(
      Object.entries(operaciones).map(([id, o]) => [id, { secuencia: o.secuencia, rechazada: o.rechazada ?? false }]),
    ),
  }
}

describe('conciliación por secuencia procesada (D1, D2)', () => {
  it('una venta aceptada que el bootstrap todavía no incluye (sin marca) sigue descontando: 48 (RUT-04)', () => {
    const c = conciliacion(null, { 'op-1': { secuencia: 1 } })
    expect(stockDisponible(63, [venta(15)], VINO, JORNADA, c)).toBe(48)
  })

  it('con la marca 7 y la venta en la secuencia 5 el bootstrap ya la incluye: 48 y no 33 (INV-06)', () => {
    const c = conciliacion(7, { 'op-1': { secuencia: 5 } })
    expect(stockDisponible(48, [venta(15)], VINO, JORNADA, c)).toBe(48)
    expect(saldoConsiderado('150000.00', [debito('70000.00')], CLIENTE, JORNADA, c)).toBe('150000.00')
  })

  it('respuesta perdida: la marca cubre la venta aunque el teléfono nunca supo su resultado: 48 (SYN-06)', () => {
    const c = conciliacion(9, { 'op-1': { secuencia: 9 } })
    expect(stockDisponible(48, [venta(15)], VINO, JORNADA, c)).toBe(48)
  })

  it('con la marca 7 y operaciones 7 y 8 cuenta solo la 8 (límite exacto)', () => {
    const c = conciliacion(7, { 'op-7': { secuencia: 7 }, 'op-8': { secuencia: 8 } })
    const movimientos = [venta(10, { operation_id: 'op-7' }), venta(4, { operation_id: 'op-8' })]
    expect(stockDisponible(50, movimientos, VINO, JORNADA, c)).toBe(46)
    const debitos = [debito('100.00', { operation_id: 'op-7' }), debito('30.50', { operation_id: 'op-8' })]
    expect(saldoConsiderado('1000.00', debitos, CLIENTE, JORNADA, c)).toBe('1030.50')
  })

  it('la cobranza sigue la misma regla (COB-04)', () => {
    const c = conciliacion(7, { 'op-1': { secuencia: 5 }, 'op-2': { secuencia: 8 } })
    const movimientos = [credito('20000.00', { operation_id: 'op-1' }), credito('5000.00', { operation_id: 'op-2' })]
    expect(saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)).toBe('95000.00')
  })

  it('una venta rechazada sigue descontando aunque la marca la cubra (D2, SYN-06)', () => {
    const c = conciliacion(9, { 'op-1': { secuencia: 3, rechazada: true } })
    expect(stockDisponible(63, [venta(15)], VINO, JORNADA, c)).toBe(48)
    expect(saldoConsiderado('100000.00', [debito('70000.00')], CLIENTE, JORNADA, c)).toBe('170000.00')
  })

  it('una venta rechazada de 50.000 cobrada 50.000 en el momento cuenta completa: el saldo no cambia y el stock sigue descontado (D2, precisión 2026-11-02)', () => {
    const c = conciliacion(9, { 'op-1': { secuencia: 3, rechazada: true } })
    const movimientos = [debito('50000.00'), credito('50000.00'), venta(15)]
    expect(saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)).toBe('100000.00')
    expect(stockDisponible(63, movimientos, VINO, JORNADA, c)).toBe(48)
  })

  it('la precisión de la rechazada vale por operación: otra aceptada y cubierta por la marca no cuenta', () => {
    const c = conciliacion(9, { 'op-1': { secuencia: 3, rechazada: true }, 'op-2': { secuencia: 4 } })
    const movimientos = [debito('50000.00'), credito('20000.00'), credito('7000.00', { operation_id: 'op-2' })]
    expect(saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)).toBe('130000.00')
  })

  it('sin marca (bootstrap anterior al 22c) cuenta todo, como antes', () => {
    const c = conciliacion(null, { 'op-1': { secuencia: 1 }, 'op-2': { secuencia: 2 } })
    expect(stockDisponible(63, [venta(15), venta(5, { operation_id: 'op-2' })], VINO, JORNADA, c)).toBe(43)
  })

  it('un movimiento sin operación en la cola cuenta (no hay evidencia de que el servidor lo tenga)', () => {
    expect(stockDisponible(63, [venta(15)], VINO, JORNADA, conciliacion(9, {}))).toBe(48)
  })

  it('otra jornada nunca cuenta, ni con la marca ni sin ella', () => {
    const c = conciliacion(null, { 'op-1': { secuencia: 1 } })
    expect(stockDisponible(63, [venta(15, { jornada_id: 'jornada-vieja' })], VINO, JORNADA, c)).toBe(63)
  })

  it('doble sincronización: aplicar la misma conciliación dos veces da lo mismo', () => {
    const c = conciliacion(7, { 'op-1': { secuencia: 5 }, 'op-2': { secuencia: 8 } })
    const movimientos = [venta(15, { operation_id: 'op-1' }), venta(3, { operation_id: 'op-2' })]
    const una = stockDisponible(48, movimientos, VINO, JORNADA, c)
    expect(stockDisponible(48, movimientos, VINO, JORNADA, c)).toBe(una)
    expect(una).toBe(45)
  })

  it('INV-04: el stock sigue entero y un stock negativo se conserva negativo', () => {
    expect(stockDisponible(5, [venta(15)], VINO, JORNADA, conciliacion(null, {}))).toBe(-10)
  })

  it('movimientosQueCuentan devuelve solo los que cuentan (sirve para la leyenda)', () => {
    const c = conciliacion(7, { 'op-1': { secuencia: 5 }, 'op-2': { secuencia: 8 } })
    const cuentan = movimientosQueCuentan(
      [venta(1, { operation_id: 'op-1' }), venta(2, { operation_id: 'op-2' })],
      JORNADA,
      c,
    )
    expect(cuentan.map((m) => m.operation_id)).toEqual(['op-2'])
    expect(movimientosQueCuentan([], JORNADA, c)).toEqual([])
  })
})

describe('stockDeTodos (RUT-04, INV-04)', () => {
  it('arma el disponible de cada producto, incluso uno sin fila de stock', () => {
    const c = conciliacion(7, { 'op-1': { secuencia: 5 }, 'op-2': { secuencia: 8 } })
    const movimientos = [
      venta(15, { operation_id: 'op-1' }),
      venta(3, { operation_id: 'op-2' }),
      venta(2, { operation_id: 'op-2', producto_id: 'sin-fila' }),
    ]
    const stock = stockDeTodos(
      [
        { producto_id: VINO, cantidad_base: 48 },
        { producto_id: 'otro', cantidad_base: 10 },
      ],
      movimientos,
      JORNADA,
      c,
    )
    expect(Object.fromEntries(stock)).toEqual({ [VINO]: 45, otro: 10, 'sin-fila': -2 })
  })
})

/**
 * Change 22d, tarea 7.1 (spec `sync/cola-local`, «La anulación local cuenta en el saldo y el
 * stock locales», sus ocho escenarios; D7; CRE-08, RUT-04, VTA-22, INV-19, SYN-06, INV-06).
 */
function conAnulaciones(
  secuenciaProcesada: number | null,
  operaciones: Record<
    string,
    { secuencia: number; rechazada?: boolean; anulacion?: { ventaRechazada: boolean } }
  >,
): Conciliacion {
  return {
    secuenciaProcesada,
    operaciones: new Map(
      Object.entries(operaciones).map(([id, o]) => [
        id,
        {
          secuencia: o.secuencia,
          rechazada: o.rechazada ?? false,
          ...(o.anulacion === undefined ? {} : { anulacion: o.anulacion }),
        },
      ]),
    ),
  }
}

const anulacionStock = (cantidad: number, extra: Partial<MovimientoLocal> = {}) =>
  mov({ operation_id: 'op-anul', tipo: 'ANULACION_STOCK', producto_id: VINO, cantidad_base: cantidad, ...extra })
const anulacionCredito = (importe: string) =>
  mov({ operation_id: 'op-anul', tipo: 'ANULACION_CREDITO', cliente_id: CLIENTE, importe })
const anulacionCobranza = (importe: string) =>
  mov({ operation_id: 'op-anul', tipo: 'ANULACION_COBRANZA_DEBITO', cliente_id: CLIENTE, importe })

describe('la anulación local cuenta en el saldo y el stock locales (D7, INV-19)', () => {
  const ANULACION_PENDIENTE = { 'op-1': { secuencia: 7 }, 'op-anul': { secuencia: 8, anulacion: { ventaRechazada: false } } }

  it('stock: 63 tras vender 15 y anular (RUT-04, VTA-21)', () => {
    const c = conAnulaciones(null, ANULACION_PENDIENTE)
    expect(stockDisponible(63, [venta(15), anulacionStock(15)], VINO, JORNADA, c)).toBe(63)
    expect(stockDisponible(63, [venta(15), anulacionStock(15)], VINO, JORNADA, SIN_CONCILIACION)).toBe(63)
  })

  it('crédito con devolución: límite 200.000, saldo 100.000 y disponible 100.000 (CRE-08, VTA-22)', () => {
    const c = conAnulaciones(null, ANULACION_PENDIENTE)
    const movimientos = [debito('70000.00'), credito('20000.00'), anulacionCredito('70000.00'), anulacionCobranza('20000.00')]
    const saldo = saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)
    expect(saldo).toBe('100000.00')
    expect(creditoDisponibleLocal('200000.00', saldo)).toBe('100000.00')
  })

  it('crédito sin devolución: saldo 80.000, los 20.000 cobrados quedan a favor (CRE-08, VTA-22)', () => {
    const c = conAnulaciones(null, ANULACION_PENDIENTE)
    const movimientos = [debito('70000.00'), credito('20000.00'), anulacionCredito('70000.00')]
    expect(saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)).toBe('80000.00')
  })

  it('venta incluida en el bootstrap (marca 7, 48 botellas) y anulación pendiente (secuencia 8): 63 (SYN-11)', () => {
    const c = conAnulaciones(7, ANULACION_PENDIENTE)
    expect(stockDisponible(48, [venta(15), anulacionStock(15)], VINO, JORNADA, c)).toBe(63)
  })

  it('anulación incluida en el bootstrap (marca 8, 63 botellas): 63 y no 78 (INV-06)', () => {
    const c = conAnulaciones(8, ANULACION_PENDIENTE)
    expect(stockDisponible(63, [venta(15), anulacionStock(15)], VINO, JORNADA, c)).toBe(63)
  })

  it('anulación rechazada: no cuenta; con el bootstrap que ya incluye la anulación de administración: 63 (SYN-06)', () => {
    const c = conAnulaciones(8, {
      'op-1': { secuencia: 7 },
      'op-anul': { secuencia: 8, rechazada: true, anulacion: { ventaRechazada: false } },
    })
    expect(stockDisponible(63, [venta(15), anulacionStock(15)], VINO, JORNADA, c)).toBe(63)
    // Con una marca que no cubre la venta, la venta cuenta y la anulación rechazada sigue sin contar.
    const sinCubrir = conAnulaciones(6, {
      'op-1': { secuencia: 7 },
      'op-anul': { secuencia: 8, rechazada: true, anulacion: { ventaRechazada: false } },
    })
    expect(stockDisponible(63, [venta(15), anulacionStock(15)], VINO, JORNADA, sinCubrir)).toBe(48)
    expect(
      saldoConsiderado('100000.00', [debito('70000.00'), anulacionCredito('70000.00')], CLIENTE, JORNADA, sinCubrir),
    ).toBe('170000.00')
  })

  it('sin marca (bootstrap anterior al 22c) una anulación rechazada tampoco cuenta, la aceptada sí', () => {
    const rechazada = conAnulaciones(null, {
      'op-1': { secuencia: 7 },
      'op-anul': { secuencia: 8, rechazada: true, anulacion: { ventaRechazada: false } },
    })
    expect(stockDisponible(48, [anulacionStock(15)], VINO, JORNADA, rechazada)).toBe(48)
    expect(stockDisponible(48, [anulacionStock(15)], VINO, JORNADA, conAnulaciones(null, ANULACION_PENDIENTE))).toBe(63)
  })

  it('venta y anulación rechazadas: cuentan las dos y se compensan, el disponible es el del bootstrap (SYN-09)', () => {
    const c = conAnulaciones(9, {
      'op-1': { secuencia: 7, rechazada: true },
      'op-anul': { secuencia: 8, rechazada: true, anulacion: { ventaRechazada: true } },
    })
    expect(stockDisponible(63, [venta(15), anulacionStock(15)], VINO, JORNADA, c)).toBe(63)
    expect(
      saldoConsiderado('100000.00', [debito('70000.00'), anulacionCredito('70000.00')], CLIENTE, JORNADA, c),
    ).toBe('100000.00')
  })

  it('doble sincronización: el mismo resultado dos veces no cambia el saldo ni el stock (INV-06, SYN-02)', () => {
    const c = conAnulaciones(8, ANULACION_PENDIENTE)
    const movimientos = [venta(15), anulacionStock(15), debito('70000.00'), anulacionCredito('70000.00')]
    const una = [stockDisponible(63, movimientos, VINO, JORNADA, c), saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)]
    const otra = [stockDisponible(63, movimientos, VINO, JORNADA, c), saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)]
    expect(otra).toEqual(una)
    expect(una).toEqual([63, '100000.00'])
  })

  it('stockDeTodos suma el ingreso de la anulación y un producto solo anulado parte de cero', () => {
    const c = conAnulaciones(null, ANULACION_PENDIENTE)
    const stock = stockDeTodos(
      [{ producto_id: VINO, cantidad_base: 48 }],
      [anulacionStock(15), anulacionStock(2, { producto_id: 'sin-fila' })],
      JORNADA,
      c,
    )
    expect(Object.fromEntries(stock)).toEqual({ [VINO]: 63, 'sin-fila': 2 })
  })
})

/**
 * Change 23, tarea 5.1 (spec `sync/cola-local`, «La cobranza local cuenta en el saldo local»;
 * D6; CRE-08, CRE-01, COB-04, SYN-06, SYN-11, INV-06, CC-04): la cobranza independiente cuenta
 * desde que se confirma, por la regla de la secuencia procesada; rechazada, deja de contar. El
 * cobro de una venta rechazada sigue la regla de su venta.
 */
function conCobranzas(
  secuenciaProcesada: number | null,
  operaciones: Record<string, { secuencia: number; rechazada?: boolean; independiente?: boolean }>,
): Conciliacion {
  return {
    secuenciaProcesada,
    operaciones: new Map(
      Object.entries(operaciones).map(([id, o]) => [
        id,
        {
          secuencia: o.secuencia,
          rechazada: o.rechazada ?? false,
          ...(o.independiente === true ? { cobranzaIndependiente: true } : {}),
        },
      ]),
    ),
  }
}

const cobranza = (importe: string, extra: Partial<MovimientoLocal> = {}) =>
  credito(importe, { operation_id: 'op-cob', ...extra })

describe('la cobranza local cuenta en el saldo local (D6)', () => {
  it('saldo 150.000 y una cobranza de 50.000 sin enviar: saldo 100.000 y disponible 100.000 con límite 200.000 (CRE-08, CRE-01)', () => {
    const c = conCobranzas(null, { 'op-cob': { secuencia: 8, independiente: true } })
    const saldo = saldoConsiderado('150000.00', [cobranza('50000.00')], CLIENTE, JORNADA, c)

    expect(saldo).toBe('100000.00')
    expect(creditoDisponibleLocal('200000.00', saldo)).toBe('100000.00')
  })

  it('incluida en el bootstrap (marca 8, saldo 100.000) no se cuenta dos veces: 100.000 y no 50.000 (INV-06, SYN-11)', () => {
    const c = conCobranzas(8, { 'op-cob': { secuencia: 8, independiente: true } })

    expect(saldoConsiderado('100000.00', [cobranza('50000.00')], CLIENTE, JORNADA, c)).toBe('100000.00')
  })

  it('pendiente después de actualizar los datos (marca 7, saldo 150.000, secuencia 8): 100.000 (SYN-11)', () => {
    const c = conCobranzas(7, { 'op-cob': { secuencia: 8, independiente: true } })

    expect(saldoConsiderado('150000.00', [cobranza('50000.00')], CLIENTE, JORNADA, c)).toBe('100000.00')
  })

  it('rechazada: no cuenta, con o sin marca que la cubra (CRE-08, SYN-06)', () => {
    const rechazada = { 'op-cob': { secuencia: 8, rechazada: true, independiente: true } }

    expect(saldoConsiderado('150000.00', [cobranza('50000.00')], CLIENTE, JORNADA, conCobranzas(9, rechazada))).toBe('150000.00')
    expect(saldoConsiderado('150000.00', [cobranza('50000.00')], CLIENTE, JORNADA, conCobranzas(null, rechazada))).toBe('150000.00')
    expect(saldoConsiderado('150000.00', [cobranza('50000.00')], CLIENTE, JORNADA, conCobranzas(7, rechazada))).toBe('150000.00')
  })

  it('rechazada y otra aceptada del mismo cliente: solo cuenta la aceptada', () => {
    const c = conCobranzas(7, {
      'op-cob': { secuencia: 8, rechazada: true, independiente: true },
      'op-cob-2': { secuencia: 9, independiente: true },
    })
    const movimientos = [cobranza('50000.00'), credito('10000.00', { operation_id: 'op-cob-2' })]

    expect(saldoConsiderado('150000.00', movimientos, CLIENTE, JORNADA, c)).toBe('140000.00')
  })

  it('el cobro de una venta rechazada sigue contando completo con su venta (CRE-08, ADR-065)', () => {
    // Sin `cobranzaIndependiente`: es el cobro en el momento de la venta, con el operation_id de la venta.
    const c = conCobranzas(9, { 'op-1': { secuencia: 3, rechazada: true } })
    const movimientos = [debito('50000.00'), credito('50000.00')]

    expect(saldoConsiderado('100000.00', movimientos, CLIENTE, JORNADA, c)).toBe('100000.00')
    expect(saldoConsiderado('100000.00', [debito('50000.00')], CLIENTE, JORNADA, c)).toBe('150000.00')
  })

  it('saldo a favor: debe 150.000, cobra 160.000 y queda -10.000 (COB-01, CC-04)', () => {
    const c = conCobranzas(null, { 'op-cob': { secuencia: 8, independiente: true } })
    const saldo = saldoConsiderado('150000.00', [cobranza('160000.00')], CLIENTE, JORNADA, c)

    expect(saldo).toBe('-10000.00')
    // Un saldo a favor deja más crédito disponible que el límite.
    expect(creditoDisponibleLocal('200000.00', saldo)).toBe('210000.00')
  })

  it('doble sincronización: el mismo resultado dos veces no cambia el saldo (INV-06, SYN-02)', () => {
    const c = conCobranzas(8, { 'op-cob': { secuencia: 8, independiente: true } })
    const una = saldoConsiderado('100000.00', [cobranza('50000.00')], CLIENTE, JORNADA, c)
    const otra = saldoConsiderado('100000.00', [cobranza('50000.00')], CLIENTE, JORNADA, c)

    expect([una, otra]).toEqual(['100000.00', '100000.00'])
  })

  it('movimientosQueCuentan deja afuera la cobranza rechazada (sirve para la leyenda)', () => {
    const c = conCobranzas(null, { 'op-cob': { secuencia: 8, rechazada: true, independiente: true } })

    expect(movimientosQueCuentan([cobranza('50000.00'), debito('10.00')], JORNADA, c)).toHaveLength(1)
  })
})

describe('el rechazo resuelto por administración deja de contar (change 25, D8; CRE-08, SYN-09, RUT-04)', () => {
  const resuelta = (secuencia: number): Conciliacion => ({
    secuenciaProcesada: 9,
    operaciones: new Map([['op-1', { secuencia, rechazada: true, resuelta: true }]]),
  })

  it('stock, débito y cobro en el momento de una venta rechazada resuelta no cuentan', () => {
    const c = resuelta(3)
    expect(stockDisponible(48, [venta(15)], VINO, JORNADA, c)).toBe(48)
    expect(saldoConsiderado('1000.00', [debito('500.00'), credito('100.00')], CLIENTE, JORNADA, c)).toBe('1000.00')
  })

  it('la misma venta rechazada sin resolver sigue contando completa', () => {
    const c = conciliacion(9, { 'op-1': { secuencia: 3, rechazada: true } })
    expect(stockDisponible(48, [venta(15)], VINO, JORNADA, c)).toBe(33)
    expect(saldoConsiderado('1000.00', [debito('500.00'), credito('100.00')], CLIENTE, JORNADA, c)).toBe('1400.00')
  })
})
