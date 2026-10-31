import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import {
  leerSaldoConsiderado,
  leerStockDisponible,
} from '../../../../../src/areas/ruta/datos/disponibles'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
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
