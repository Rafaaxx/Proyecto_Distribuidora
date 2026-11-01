import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { leerSaldoConsiderado, leerStockDisponible } from '../../../src/areas/ruta/datos/disponibles'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { aplicarResultados } from '../../../src/sync/aplicarResultados'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../utils/datosParaVender'
import { sembrarVenta } from '../utils/sembrarVenta'

/**
 * Change 22b, tareas 3.1 y 3.2 (specs `sync/motor-de-sincronizacion`, «El resultado de cada
 * operación se escribe en el teléfono», y `sync/cola-local`, «Las operaciones locales no se
 * borran hasta su resultado» y «El saldo y el stock locales suman lo que hizo el teléfono»;
 * `design.md` D3, D4; cita INV-01, SYN-04, SYN-09, RUT-04, CRE-08).
 */
const AHORA = new Date('2026-11-01T12:00:00.000Z')

function resultado(operation_id: string, estado: string, error_codigo: string | null = null) {
  return { operation_id, estado, resultado: null, error_codigo }
}

async function contar() {
  return {
    ventas: await baseLocal.ventas.count(),
    cobranzas: await baseLocal.cobranzas.count(),
    movimientos: await baseLocal.movimientos_locales.count(),
    cola: await baseLocal.cola.count(),
  }
}

describe('aplicar los resultados del lote (tarea 3.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarComando(comandoDePrueba(1))
    await sembrarComando(comandoDePrueba(2))
    await sembrarComando(comandoDePrueba(3))
    await sembrarComando(comandoDePrueba(4))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('por operation_id (no por posición): la cola toma estado, código y momento; la venta, su estado de envío', async () => {
    await aplicarResultados(
      [
        resultado('op-3', 'RECHAZADO', 'JORNADA_INEXISTENTE'),
        resultado('op-1', 'ACEPTADO'),
        resultado('op-2', 'ACEPTADO_CON_OBSERVACIONES'),
      ],
      AHORA,
    )

    const cola = await baseLocal.cola.orderBy('secuencia').toArray()
    expect(cola.map((c) => c.estado)).toEqual(['ACEPTADO', 'ACEPTADO_CON_OBSERVACIONES', 'RECHAZADO', 'PENDIENTE'])
    expect(cola[2]).toMatchObject({ error_codigo: 'JORNADA_INEXISTENTE', resultado_en: AHORA.toISOString() })
    expect(cola[0]?.error_codigo ?? null).toBeNull()
    const ventas = await baseLocal.ventas.orderBy('numero').toArray()
    expect(ventas.map((v) => v.estado_envio)).toEqual(['ACEPTADA', 'CON_OBSERVACIONES', 'RECHAZADA', 'PENDIENTE'])
  })

  it('ERROR_TRANSITORIO y lo no procesado quedan PENDIENTE', async () => {
    await aplicarResultados([resultado('op-1', 'ERROR_TRANSITORIO'), resultado('op-2', 'ACEPTADO')], AHORA)

    const cola = await baseLocal.cola.orderBy('secuencia').toArray()
    expect(cola.map((c) => c.estado)).toEqual(['PENDIENTE', 'ACEPTADO', 'PENDIENTE', 'PENDIENTE'])
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('PENDIENTE')
  })

  it('un operation_id desconocido se ignora y se avisa en consola; los demás se aplican', async () => {
    const aviso = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    const resumen = await aplicarResultados(
      [resultado('op-desconocido', 'ACEPTADO'), resultado('op-1', 'ACEPTADO')],
      AHORA,
    )

    expect(aviso).toHaveBeenCalledOnce()
    expect(resumen).toEqual({ aplicados: 1, ignorados: 1 })
    expect((await baseLocal.cola.get(1))?.estado).toBe('ACEPTADO')
  })

  it('nada se borra: venta, cobranza, movimientos y comando siguen (SYN-09)', async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a')
    const antes = await contar()

    await aplicarResultados([resultado('op-a', 'RECHAZADO', 'JORNADA_INEXISTENTE')], AHORA)

    expect(await contar()).toEqual(antes)
    expect((await baseLocal.ventas.get('venta-a'))?.estado_envio).toBe('RECHAZADA')
    expect(antes.movimientos).toBeGreaterThan(0)
  })

  it('es una sola transacción: con una falla después del primer resultado ninguno cambia (INV-01)', async () => {
    const original = baseLocal.ventas.where.bind(baseLocal.ventas)
    let llamadas = 0
    vi.spyOn(baseLocal.ventas, 'where').mockImplementation(((...args: Parameters<typeof original>) => {
      llamadas += 1
      if (llamadas === 2) throw new Error('falla inyectada')
      return original(...args)
    }) as typeof original)

    await expect(
      aplicarResultados([resultado('op-1', 'ACEPTADO'), resultado('op-2', 'ACEPTADO')], AHORA),
    ).rejects.toThrow('falla inyectada')

    vi.restoreAllMocks()
    expect((await baseLocal.cola.orderBy('secuencia').toArray()).map((c) => c.estado)).toEqual([
      'PENDIENTE',
      'PENDIENTE',
      'PENDIENTE',
      'PENDIENTE',
    ])
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('PENDIENTE')
  })

  it('aplicar dos veces el mismo resultado deja lo mismo (el momento del primero se conserva)', async () => {
    await aplicarResultados([resultado('op-1', 'ACEPTADO')], AHORA)
    await aplicarResultados([resultado('op-1', 'ACEPTADO')], new Date('2026-11-01T13:00:00.000Z'))

    expect(await baseLocal.cola.get(1)).toMatchObject({ estado: 'ACEPTADO', resultado_en: AHORA.toISOString() })
  })
})

describe('el stock y el saldo locales siguen contando la venta aceptada (tarea 3.2; D4)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  it('«Venta ya enviada»: después del ACEPTADO el stock (20 − 15 = 5) y el saldo se mantienen (RUT-04, CRE-08)', async () => {
    await sembrarVenta('a')
    const stockAntes = await leerStockDisponible(IDS_DE_PRUEBA.producto)
    const saldoAntes = await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)
    expect(stockAntes).toBe(5)

    await aplicarResultados([resultado('op-a', 'ACEPTADO')], AHORA)

    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(5)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe(saldoAntes)
    const movimientos = await baseLocal.movimientos_locales.toArray()
    expect(movimientos.every((m) => m.estado_operacion === 'PENDIENTE')).toBe(true)
  })

  it('con la venta rechazada tampoco se tocan los movimientos locales (los concilia el 22c)', async () => {
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(14)

    await aplicarResultados([resultado('op-b', 'RECHAZADO', 'JORNADA_INEXISTENTE')], AHORA)

    expect(await leerStockDisponible(IDS_DE_PRUEBA.producto)).toBe(14)
  })
})
