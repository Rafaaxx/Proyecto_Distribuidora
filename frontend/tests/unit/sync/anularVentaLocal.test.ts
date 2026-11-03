import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { leerSaldoConsiderado, leerStockDisponible } from '../../../src/areas/ruta/datos/disponibles'
import { ErrorDeAnulacionLocal } from '../../../src/domain/ruta/anulacionLocal'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarResultados } from '../../../src/sync/aplicarResultados'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { anularVentaLocal, type EntradaDeAnulacionConfirmada } from '../../../src/sync/anularVentaLocal'
import { CLAVE_ULTIMA_SECUENCIA } from '../../../src/sync/confirmarVentaLocal'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../utils/datosParaVender'
import { sembrarVenta } from '../utils/sembrarVenta'

/**
 * Change 22d, tarea 6.2 (spec `sync/cola-local`, «Anular una venta local es una sola transacción»,
 * sus cuatro escenarios; `design.md` D4, D6; cita INV-01, INV-06, SYN-01, SYN-03, VTA-22).
 * La venta de prueba: 2 cajas + 3 unidades de Gaseosa (15 unidades base, $120.000) sobre un stock
 * de 20 en el bootstrap.
 */
const USUARIO = '00000000-0000-4000-8000-000000000001'
const AHORA = new Date('2026-11-03T12:30:00.000Z')

function entrada(sufijo: string, cambios: Partial<EntradaDeAnulacionConfirmada> = {}): EntradaDeAnulacionConfirmada {
  return {
    ventaId: `venta-${sufijo}`,
    motivo: { id: IDS_DE_PRUEBA.motivo, nombre: 'Error de carga' },
    observacion: null,
    devuelveDinero: null,
    operationId: `op-anul-${sufijo}`,
    usuarioId: USUARIO,
    dispositivoId: 'disp-1',
    ahora: AHORA,
    appVersion: '1.0.0',
    ...cambios,
  }
}

async function contar() {
  return {
    ventas: await baseLocal.ventas.count(),
    anulaciones: await baseLocal.anulaciones.count(),
    movimientos: await baseLocal.movimientos_locales.count(),
    cola: await baseLocal.cola.count(),
    ultimaSecuencia: (await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor,
  }
}

describe('anular una venta local es una sola transacción (change 22d, tarea 6.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('escribe anulación, ingreso de la mercadería, crédito del total y el comando VENTA_ANULAR OFFLINE con la secuencia siguiente (VTA-24, SYN-01)', async () => {
    await sembrarVenta('a')
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBe('1')

    const r = await anularVentaLocal(entrada('a', { observacion: 'Se cargó mal' }))

    expect(r.repetida).toBe(false)
    expect(r.anulacion).toMatchObject({
      venta_id: 'venta-a',
      operation_id: 'op-anul-a',
      estado_envio: 'PENDIENTE',
      motivo_nombre: 'Error de carga',
      observacion: 'Se cargó mal',
      devuelve_dinero: null,
    })
    expect(await baseLocal.anulaciones.get('venta-a')).toEqual(r.anulacion)
    expect(r.comando).toMatchObject({ secuencia: 2, operation_id: 'op-anul-a', estado: 'PENDIENTE' })
    expect(r.comando.sobre).toMatchObject({
      tipo: 'VENTA_ANULAR',
      version: 1,
      modo: 'OFFLINE',
      secuencia: 2,
      usuario_id: USUARIO,
      dispositivo_id: 'disp-1',
      contenido: { venta_id: 'venta-a', motivo_id: IDS_DE_PRUEBA.motivo, observacion: 'Se cargó mal' },
    })
    expect(r.comando.sobre.contenido).not.toHaveProperty('devuelve_dinero')
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBe('2')

    const delaAnulacion = await baseLocal.movimientos_locales.where('operation_id').equals('op-anul-a').toArray()
    expect(delaAnulacion.map((m) => [m.tipo, m.cantidad_base, m.importe])).toEqual([
      ['ANULACION_STOCK', 12, null],
      ['ANULACION_STOCK', 3, null],
      ['ANULACION_CREDITO', null, '120000.00'],
    ])
    // El stock y el saldo locales quedan como antes de vender (INV-19).
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(20)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1500.50')
  })

  it('con cobro y devolución agrega el débito de lo cobrado y el sobre lleva devuelve_dinero true; sin devolución no (VTA-22)', async () => {
    await sembrarVenta('a', { cobro: '20000.00', cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cobro: '20000.00', cajas: 1, unidades: 0 })

    const con = await anularVentaLocal(entrada('a', { devuelveDinero: true }))
    const sin = await anularVentaLocal(entrada('b', { devuelveDinero: false }))

    expect(con.comando.sobre.contenido).toMatchObject({ devuelve_dinero: true })
    expect(sin.comando.sobre.contenido).toMatchObject({ devuelve_dinero: false })
    const tipos = async (op: string) =>
      (await baseLocal.movimientos_locales.where('operation_id').equals(op).toArray()).map((m) => m.tipo)
    expect(await tipos('op-anul-a')).toEqual(['ANULACION_STOCK', 'ANULACION_CREDITO', 'ANULACION_COBRANZA_DEBITO'])
    expect(await tipos('op-anul-b')).toEqual(['ANULACION_STOCK', 'ANULACION_CREDITO'])
  })

  it('con cobro y sin elegir la devolución no escribe nada (DEVOLUCION_REQUERIDA)', async () => {
    await sembrarVenta('a', { cobro: '20000.00' })
    const antes = await contar()

    await expect(anularVentaLocal(entrada('a', { devuelveDinero: null }))).rejects.toMatchObject({
      codigo: 'DEVOLUCION_REQUERIDA',
    })
    expect(await contar()).toEqual(antes)
  })

  it('falla a mitad: no queda anulación, movimiento ni comando y la secuencia no avanza (INV-01)', async () => {
    await sembrarVenta('a')
    const antes = await contar()
    vi.spyOn(baseLocal.cola, 'add').mockRejectedValue(new Error('falla inyectada'))

    await expect(anularVentaLocal(entrada('a'))).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect(await contar()).toEqual(antes)
    expect(antes.ultimaSecuencia).toBe('1')
    expect(await baseLocal.anulaciones.get('venta-a')).toBeUndefined()
  })

  it('otra falla (en los movimientos) tampoco deja la anulación escrita (INV-01)', async () => {
    await sembrarVenta('a')
    const antes = await contar()
    vi.spyOn(baseLocal.movimientos_locales, 'bulkAdd').mockRejectedValue(new Error('falla en movimientos'))

    await expect(anularVentaLocal(entrada('a'))).rejects.toThrow('falla en movimientos')

    vi.restoreAllMocks()
    expect(await contar()).toEqual(antes)
  })

  it('reconfirmar la misma venta devuelve la anulación existente sin escribir nada (INV-06, SYN-02)', async () => {
    await sembrarVenta('a')
    const primera = await anularVentaLocal(entrada('a'))
    const antes = await contar()

    const otra = await anularVentaLocal(entrada('a', { operationId: 'op-anul-distinto' }))

    expect(otra.repetida).toBe(true)
    expect(otra.anulacion).toEqual(primera.anulacion)
    expect(otra.comando).toEqual(primera.comando)
    expect(await contar()).toEqual(antes)
  })

  it('la anulación de una venta «Sin enviar» queda detrás de ella: venta 1, anulación 2 y se envían en ese orden (SYN-03)', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    expect((await baseLocal.cola.get(2))?.estado).toBe('PENDIENTE')

    const r = await anularVentaLocal(entrada('a'))

    expect(r.comando.secuencia).toBe(3)
    const pendientes = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).sort(
      (x, y) => x.secuencia - y.secuencia,
    )
    expect(pendientes.map((c) => [c.secuencia, c.sobre.tipo])).toEqual([
      [1, 'VENTA_CONFIRMAR'],
      [2, 'VENTA_CONFIRMAR'],
      [3, 'VENTA_ANULAR'],
    ])
  })

  it('no anula una venta inexistente, de otra jornada ni «Rechazada»: VENTA_NO_ANULABLE y nada escrito (D5)', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    await baseLocal.ventas.update('venta-a', { jornada_id: 'otra-jornada' })
    await baseLocal.ventas.update('venta-b', { estado_envio: 'RECHAZADA' })
    const antes = await contar()

    for (const ventaId of ['venta-a', 'venta-b', 'venta-fantasma']) {
      const error = await anularVentaLocal(entrada('x', { ventaId })).catch((e: unknown) => e)
      expect(error).toBeInstanceOf(ErrorDeAnulacionLocal)
      expect((error as ErrorDeAnulacionLocal).codigo).toBe('VENTA_NO_ANULABLE')
    }
    expect(await contar()).toEqual(antes)
  })

  it('venta y anulación rechazadas se compensan al leer el stock y el saldo; solo la anulación rechazada deja la venta descontando (D7)', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await anularVentaLocal(entrada('a'))
    const resultado = (op: string, codigo: string) => ({ operation_id: op, estado: 'RECHAZADO', resultado: null, error_codigo: codigo })

    await aplicarResultados([resultado('op-anul-a', 'VENTA_INEXISTENTE')], AHORA)
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(14)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('49500.50')

    await aplicarResultados([resultado('op-a', 'JORNADA_AJENA')], AHORA)
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(20)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1500.50')
  })
})
