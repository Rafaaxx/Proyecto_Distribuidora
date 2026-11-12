import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import {
  leerConciliacion,
  leerSaldoConsiderado,
  leerStockDeTodos,
  leerStockDisponible,
} from '../../../../../src/areas/ruta/datos/disponibles'
import { leerDatosParaVender } from '../../../../../src/areas/ruta/datos/paraVender'
import { baseLocal, type MovimientoLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapDePrueba, ID } from '../../../utils/bootstrapDePrueba'

/** Change 22a, tarea 5.1: lectura de Dexie de los disponibles (D5; CRE-08, RUT-04). */
const CLIENTE = ID(101)

describe('lectura de saldo y stock locales', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
  })

  it('suma los movimientos de la jornada del bootstrap al saldo del cliente (CRE-08)', async () => {
    const base = { jornada_id: ID(2), estado_operacion: 'PENDIENTE' as const, producto_id: null, cantidad_base: null }
    await baseLocal.movimientos_locales.bulkAdd([
      { ...base, operation_id: 'a', tipo: 'VENTA_DEBITO', cliente_id: CLIENTE, importe: '500.00' },
      { ...base, operation_id: 'a', tipo: 'COBRANZA_CREDITO', cliente_id: CLIENTE, importe: '200.00' },
      { ...base, jornada_id: 'otra', operation_id: 'b', tipo: 'VENTA_DEBITO', cliente_id: CLIENTE, importe: '9999.00' },
    ])
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('1800.50')
  })

  it('sin movimientos el saldo es el del bootstrap y un cliente desconocido es null', async () => {
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('1500.50')
    expect(await leerSaldoConsiderado('no-existe')).toBeNull()
  })

  it('el stock disponible resta lo vendido en la jornada (RUT-04)', async () => {
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 63 })
    await baseLocal.movimientos_locales.add({
      operation_id: 'a',
      jornada_id: ID(2),
      tipo: 'VENTA_STOCK',
      producto_id: ID(30),
      cliente_id: null,
      cantidad_base: -15,
      importe: null,
      estado_operacion: 'PENDIENTE',
    })
    expect(await leerStockDisponible(ID(30))).toBe(48)
    expect(await leerStockDisponible('sin-stock')).toBe(0)
  })
})

/**
 * Change 22c, tarea 7.2 (spec `sync/cola-local`, «El saldo y el stock locales suman lo que hizo el
 * telefono»; D1, D2; CRE-08, RUT-04, COB-04, SYN-06, INV-06): los mismos escenarios contra Dexie.
 */
function movimiento(operation_id: string, parcial: Partial<MovimientoLocal>): MovimientoLocal {
  return {
    operation_id,
    jornada_id: ID(2),
    tipo: 'VENTA_STOCK',
    producto_id: ID(30),
    cliente_id: null,
    cantidad_base: -15,
    importe: null,
    estado_operacion: 'PENDIENTE',
    ...parcial,
  }
}

async function sembrarCola(operation_id: string, secuencia: number, estado: 'PENDIENTE' | 'ACEPTADO' | 'RECHAZADO') {
  await baseLocal.cola.put({ secuencia, operation_id, estado, sobre: { operation_id } as never })
}

const DEBITO = { tipo: 'VENTA_DEBITO', producto_id: null, cantidad_base: null, cliente_id: CLIENTE } as const

describe('conciliacion contra Dexie (change 22c, tarea 7.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('con la marca 7 y la venta en la secuencia 5 el stock es 48 y no 33 (INV-06, RUT-04)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 7 }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 48 })
    await baseLocal.movimientos_locales.add(movimiento('op-5', {}))
    await sembrarCola('op-5', 5, 'ACEPTADO')

    expect(await leerStockDisponible(ID(30))).toBe(48)
  })

  it('con la marca 7 y operaciones 7 y 8 cuenta solo la 8, en stock y en saldo (CRE-08)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 7 }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 50 })
    await baseLocal.movimientos_locales.bulkAdd([
      movimiento('op-7', { cantidad_base: -10 }),
      movimiento('op-8', { cantidad_base: -4 }),
      movimiento('op-7', { ...DEBITO, importe: '100.00' }),
      movimiento('op-8', { ...DEBITO, importe: '30.50' }),
    ])
    await sembrarCola('op-7', 7, 'ACEPTADO')
    await sembrarCola('op-8', 8, 'PENDIENTE')

    expect(await leerStockDisponible(ID(30))).toBe(46)
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('1531.00')
  })

  it('una venta rechazada con la marca 9 sigue descontando (D2, SYN-06)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 9 }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 63 })
    await baseLocal.movimientos_locales.add(movimiento('op-3', {}))
    await sembrarCola('op-3', 3, 'RECHAZADO')

    expect(await leerStockDisponible(ID(30))).toBe(48)
  })

  it('sin marca cuenta todo, aunque la operacion figure aceptada', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: null }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 63 })
    await baseLocal.movimientos_locales.add(movimiento('op-1', {}))
    await sembrarCola('op-1', 1, 'ACEPTADO')

    expect(await leerStockDisponible(ID(30))).toBe(48)
  })

  it('leerConciliacion arma la marca y las operaciones de la cola por operation_id', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 7 }))
    await sembrarCola('op-a', 5, 'ACEPTADO')
    await sembrarCola('op-b', 9, 'RECHAZADO')

    const c = await leerConciliacion()

    expect(c.secuenciaProcesada).toBe(7)
    expect(c.operaciones.get('op-a')).toEqual({ secuencia: 5, rechazada: false })
    expect(c.operaciones.get('op-b')).toEqual({ secuencia: 9, rechazada: true })
  })

  it('leerStockDeTodos devuelve el disponible de cada producto con la misma regla', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 7 }))
    await baseLocal.stock.bulkPut([
      { producto_id: ID(30), cantidad_base: 48 },
      { producto_id: ID(31), cantidad_base: 10 },
    ])
    await baseLocal.movimientos_locales.bulkAdd([
      movimiento('op-5', {}),
      movimiento('op-8', { cantidad_base: -3 }),
      movimiento('op-8', { producto_id: ID(31), cantidad_base: -1 }),
    ])
    await sembrarCola('op-5', 5, 'ACEPTADO')
    await sembrarCola('op-8', 8, 'PENDIENTE')

    const todos = await leerStockDeTodos()

    expect(todos.get(ID(30))).toBe(45)
    expect(todos.get(ID(31))).toBe(9)
  })

  it('sin sesion: marca nula y stock vacio', async () => {
    expect((await leerConciliacion()).secuenciaProcesada).toBeNull()
    expect((await leerStockDeTodos()).size).toBe(0)
  })
})

describe('Vender usa la misma conciliacion (change 22c, tarea 7.2; RUT-04, CRE-08)', () => {
  it('los movimientos que el bootstrap ya incluye no llegan al armado de la venta', async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 7 }))
    await baseLocal.movimientos_locales.bulkAdd([movimiento('op-5', {}), movimiento('op-8', {})])
    await sembrarCola('op-5', 5, 'ACEPTADO')
    await sembrarCola('op-8', 8, 'PENDIENTE')

    const datos = await leerDatosParaVender()

    expect(datos?.movimientos.map((m) => m.operation_id)).toEqual(['op-8'])
  })
})
