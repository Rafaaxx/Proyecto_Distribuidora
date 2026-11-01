import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import { instalarCandadosDePrueba, type CandadosDePrueba } from '../utils/candadosDePrueba'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'

/**
 * Change 22b, tarea 5.1 (spec `sync/motor-de-sincronizacion`, «Sincronizar dos veces no duplica la
 * operación»; `design.md` D12; cita **INV-06**, SYN-02): con un servidor simulado idempotente por
 * `operation_id`, dos «pestañas» (dos copias del módulo, cada una con su conexión Dexie sobre la
 * misma base, y `navigator.locks` de prueba con exclusión real), la respuesta perdida y el
 * reenvío no duplican nada.
 */
interface ServidorSimulado {
  /** Veces que el servidor HIZO la operación (idempotente: una por operation_id). */
  hechas: Map<string, number>
  lotesRecibidos: number
  /** Si es verdadero, procesa pero la respuesta no llega (corte de red). */
  perderLaProximaRespuesta: boolean
  compuerta: Promise<void> | null
}

const servidor: ServidorSimulado = {
  hechas: new Map(),
  lotesRecibidos: 0,
  perderLaProximaRespuesta: false,
  compuerta: null,
}

vi.mock('../../../src/lib/api/httpClient', () => ({
  apiFetch: vi.fn(async (_ruta: string, init: RequestInit) => {
    servidor.lotesRecibidos += 1
    const items = (JSON.parse(String(init.body)) as { items: { operation_id: string }[] }).items
    if (servidor.compuerta !== null) await servidor.compuerta
    for (const item of items) {
      if (!servidor.hechas.has(item.operation_id)) servidor.hechas.set(item.operation_id, 1)
    }
    if (servidor.perderLaProximaRespuesta) {
      servidor.perderLaProximaRespuesta = false
      throw new TypeError('Failed to fetch')
    }
    const resultados = items.map((i) => ({
      operation_id: i.operation_id,
      estado: 'ACEPTADO',
      resultado: { venta: 'misma' },
      error_codigo: null,
    }))
    return new Response(JSON.stringify({ resultados }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }),
}))

const ENTRADA = { usuarioId: 'u1', dispositivoId: 'd1' } as const

async function abrirPestana() {
  vi.resetModules()
  const modulo = await import('../../../src/sync/sincronizar')
  return modulo.crearSincronizador({ ahora: () => new Date('2026-11-01T12:00:00.000Z'), azar: () => 0.5 })
}

describe('sincronizar dos veces no duplica la operación (tarea 5.1; INV-06, SYN-02)', () => {
  let candados: CandadosDePrueba
  beforeEach(async () => {
    candados = instalarCandadosDePrueba()
    servidor.hechas.clear()
    servidor.lotesRecibidos = 0
    servidor.perderLaProximaRespuesta = false
    servidor.compuerta = null
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarComando(comandoDePrueba(1))
  })
  afterEach(() => {
    candados.restaurar()
  })

  it('(a) dos «pestañas» disparan a la vez y sale un solo lote', async () => {
    let abrir!: () => void
    servidor.compuerta = new Promise<void>((resolver) => {
      abrir = resolver
    })
    const pestanaA = await abrirPestana()
    const pestanaB = await abrirPestana()

    const a = pestanaA.sincronizar({ ...ENTRADA, origen: 'primer_plano' })
    await vi.waitFor(() => expect(servidor.lotesRecibidos).toBe(1))
    const b = await pestanaB.sincronizar({ ...ENTRADA, origen: 'primer_plano' })
    abrir()

    expect(b).toEqual({ tipo: 'otra_pestana' })
    expect(await a).toEqual({ tipo: 'completa', enviadas: 1 })
    expect(servidor.lotesRecibidos).toBe(1)
    expect(servidor.hechas.get('op-1')).toBe(1)
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('ACEPTADA')
  })

  it('(b) el servidor procesa y la respuesta se pierde: el reenvío trae el mismo resultado y la venta queda una vez ACEPTADA', async () => {
    const pestana = await abrirPestana()
    servidor.perderLaProximaRespuesta = true

    expect(await pestana.sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'transitorio' })
    expect((await baseLocal.cola.get(1))?.estado).toBe('PENDIENTE')

    expect(await pestana.sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'completa', enviadas: 1 })

    expect(servidor.lotesRecibidos).toBe(2)
    expect(servidor.hechas.get('op-1')).toBe(1)
    expect(await baseLocal.ventas.count()).toBe(1)
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('ACEPTADA')
    expect((await baseLocal.cola.get(1))?.estado).toBe('ACEPTADO')
  })

  it('(c) «Sincronizar» otra vez con todo aceptado no envía lote', async () => {
    const pestana = await abrirPestana()
    await pestana.sincronizar({ ...ENTRADA, origen: 'manual' })
    expect(servidor.lotesRecibidos).toBe(1)

    expect(await pestana.sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'completa', enviadas: 0 })

    expect(servidor.lotesRecibidos).toBe(1)
    expect(servidor.hechas.get('op-1')).toBe(1)
  })

  it('sin Web Locks las dos pestañas pueden enviar a la vez y aun así no hay efecto duplicado', async () => {
    candados.restaurar()
    Object.defineProperty(window.navigator, 'locks', { configurable: true, value: undefined })
    const pestanaA = await abrirPestana()
    const pestanaB = await abrirPestana()

    const [a, b] = await Promise.all([
      pestanaA.sincronizar({ ...ENTRADA, origen: 'manual' }),
      pestanaB.sincronizar({ ...ENTRADA, origen: 'manual' }),
    ])

    expect([a.tipo, b.tipo].every((t) => t === 'completa' || t === 'otra_pestana')).toBe(true)
    expect(servidor.hechas.get('op-1')).toBe(1)
    expect((await baseLocal.ventas.get('venta-1'))?.estado_envio).toBe('ACEPTADA')
    Reflect.deleteProperty(window.navigator, 'locks')
  })
})
