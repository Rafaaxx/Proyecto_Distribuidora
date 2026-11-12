import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { leerConciliacion, leerSaldoConsiderado, leerStockDisponible } from '../../../src/areas/ruta/datos/disponibles'
import { baseLocal, type MovimientoLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { CLAVE_RECHAZOS_RESUELTOS, leerRechazosResueltos } from '../../../src/sync/rechazosResueltos'
import { bootstrapDePrueba, ID } from '../utils/bootstrapDePrueba'

/**
 * Change 25, tarea 16.1 (spec `sync/cola-local`, sus cuatro escenarios; `design.md` D8; cita CRE-08,
 * SYN-09, INV-01, INV-06): el bootstrap guarda `rechazos_resueltos` en `meta`, en su transaccion; la
 * venta rechazada resuelta deja de contar (stock, debito y cobro en el momento) sin borrarse.
 */
const CLIENTE = ID(101)

function movimiento(operation_id: string, parcial: Partial<MovimientoLocal>): MovimientoLocal {
  return {
    operation_id,
    jornada_id: ID(2),
    tipo: 'VENTA_STOCK',
    producto_id: ID(30),
    cliente_id: null,
    cantidad_base: -12,
    importe: null,
    estado_operacion: 'PENDIENTE',
    ...parcial,
  }
}

async function sembrarCola(operation_id: string, secuencia: number, estado: 'PENDIENTE' | 'ACEPTADO' | 'RECHAZADO') {
  await baseLocal.cola.put({ secuencia, operation_id, estado, sobre: { operation_id } as never })
}

describe('rechazos resueltos en el bootstrap (change 25, tarea 16.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => vi.restoreAllMocks())

  it('aplicar el bootstrap guarda la lista en meta (SYN-09)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ rechazosResueltos: ['op-1', 'op-2'] }))

    expect(await baseLocal.meta.get(CLAVE_RECHAZOS_RESUELTOS)).toBeDefined()
    expect([...(await leerRechazosResueltos())].sort()).toEqual(['op-1', 'op-2'])
  })

  it('un bootstrap posterior reemplaza la lista, y sin lista queda vacia', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ rechazosResueltos: ['op-1'] }))
    await aplicarBootstrap(bootstrapDePrueba({ rechazosResueltos: ['op-3'] }))
    expect([...(await leerRechazosResueltos())]).toEqual(['op-3'])

    const sinCampo = bootstrapDePrueba()
    delete (sinCampo as { rechazos_resueltos?: string[] }).rechazos_resueltos
    await aplicarBootstrap(sinCampo)
    expect((await leerRechazosResueltos()).size).toBe(0)
  })

  it('no sube la version de Dexie: sigue en la 5', () => {
    expect(baseLocal.verno).toBe(5)
  })

  it('una falla a mitad deja la lista anterior y los datos anteriores (INV-01)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ rechazosResueltos: ['op-viejo'] }))
    vi.spyOn(baseLocal.stock, 'bulkPut').mockRejectedValue(new Error('falla inyectada'))

    await expect(aplicarBootstrap(bootstrapDePrueba({ rechazosResueltos: ['op-nuevo'] }))).rejects.toThrow(
      'falla inyectada',
    )

    expect([...(await leerRechazosResueltos())]).toEqual(['op-viejo'])
  })

  it('doble actualizacion con el mismo rechazo: deja de contar una sola vez (INV-06)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 9 }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 48 })
    await baseLocal.movimientos_locales.add(movimiento('op-3', {}))
    await sembrarCola('op-3', 3, 'RECHAZADO')
    expect(await leerStockDisponible(ID(30))).toBe(36)

    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 9, rechazosResueltos: ['op-3'] }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 48 })
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 9, rechazosResueltos: ['op-3'] }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 48 })

    expect(await leerStockDisponible(ID(30))).toBe(48)
  })
})

describe('la venta rechazada resuelta deja de contar (change 25, tarea 16.1; CRE-08, RUT-04)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  async function ventaRechazada(resuelta: boolean) {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 9, rechazosResueltos: resuelta ? ['op-3'] : [] }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 48 })
    await baseLocal.movimientos_locales.bulkAdd([
      movimiento('op-3', {}),
      movimiento('op-3', { tipo: 'VENTA_DEBITO', producto_id: null, cantidad_base: null, cliente_id: CLIENTE, importe: '500.00' }),
      movimiento('op-3', { tipo: 'COBRANZA_CREDITO', producto_id: null, cantidad_base: null, cliente_id: CLIENTE, importe: '100.00' }),
    ])
    await sembrarCola('op-3', 3, 'RECHAZADO')
  }

  it('resuelta: ni el stock, ni el debito, ni el cobro en el momento cuentan', async () => {
    await ventaRechazada(true)

    expect(await leerStockDisponible(ID(30))).toBe(48)
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('1500.50')
    expect(await baseLocal.movimientos_locales.where('operation_id').equals('op-3').count()).toBe(3)
  })

  it('pendiente (no resuelta): la sigue contando completa', async () => {
    await ventaRechazada(false)

    expect(await leerStockDisponible(ID(30))).toBe(36)
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('1900.50')
  })

  it('un id resuelto de una operacion NO rechazada no cambia nada (solo las rechazadas)', async () => {
    await aplicarBootstrap(bootstrapDePrueba({ secuenciaProcesada: 2, rechazosResueltos: ['op-5'] }))
    await baseLocal.stock.put({ producto_id: ID(30), cantidad_base: 48 })
    await baseLocal.movimientos_locales.add(movimiento('op-5', {}))
    await sembrarCola('op-5', 5, 'PENDIENTE')

    expect(await leerStockDisponible(ID(30))).toBe(36)
    expect((await leerConciliacion()).operaciones.get('op-5')?.resuelta).toBeUndefined()
  })

  it('la conciliacion marca resuelta solo a la rechazada resuelta', async () => {
    await ventaRechazada(true)

    expect((await leerConciliacion()).operaciones.get('op-3')).toMatchObject({ rechazada: true, resuelta: true })
  })

  it('anulacion de una venta rechazada resuelta: tampoco suma el ingreso (se compensaba con la venta)', async () => {
    await ventaRechazada(true)
    await baseLocal.ventas.put({ venta_id: 'v-3', operation_id: 'op-3', estado_envio: 'RECHAZADA' } as never)
    await baseLocal.anulaciones.put({ venta_id: 'v-3', operation_id: 'op-a', estado_envio: 'RECHAZADA' } as never)
    await baseLocal.movimientos_locales.add(movimiento('op-a', { tipo: 'ANULACION_STOCK', cantidad_base: 12 }))
    await sembrarCola('op-a', 4, 'RECHAZADO')

    expect(await leerStockDisponible(ID(30))).toBe(48)
  })
})
