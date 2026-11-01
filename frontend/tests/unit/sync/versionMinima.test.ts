import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import { instalarCandadosDePrueba } from '../utils/candadosDePrueba'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'
import {
  actualizarVersionMinima,
  CLAVE_VERSION_MINIMA,
  compararVersiones,
  estaPorDebajoDeLaMinima,
  ventaBloqueadaPorVersion,
} from '../../../src/sync/versionMinima'

/**
 * Change 22b, tarea 9.1 (spec `sync/motor-de-sincronizacion`, «Por debajo de la versión mínima se
 * envía la cola pero no se vende»; `design.md` D7; cita `02` §6.6).
 */
describe('comparación de versiones X.Y.Z (tarea 9.1)', () => {
  it('compara por números, no por texto', () => {
    expect(compararVersiones('1.2.0', '1.3.0')).toBeLessThan(0)
    expect(compararVersiones('1.10.0', '1.9.0')).toBeGreaterThan(0)
    expect(compararVersiones('2.0.0', '2.0.0')).toBe(0)
    expect(compararVersiones('1.0.10', '1.0.9')).toBeGreaterThan(0)
  })

  it('estar por debajo de la mínima solo vale con las dos versiones en formato X.Y.Z', () => {
    expect(estaPorDebajoDeLaMinima('1.2.0', '1.3.0')).toBe(true)
    expect(estaPorDebajoDeLaMinima('1.10.0', '1.9.0')).toBe(false)
    expect(estaPorDebajoDeLaMinima('1.3.0', '1.3.0')).toBe(false)
    // `dev`, texto sin formato o mínima ausente no restringen.
    expect(estaPorDebajoDeLaMinima('dev', '1.3.0')).toBe(false)
    expect(estaPorDebajoDeLaMinima('1.2.0', 'cualquiera')).toBe(false)
    expect(estaPorDebajoDeLaMinima('1.2.0', null)).toBe(false)
    expect(estaPorDebajoDeLaMinima('1.2', '1.3.0')).toBe(false)
    expect(estaPorDebajoDeLaMinima('0.0.0', '1.3.0')).toBe(true)
  })
})

describe('mínima conocida en la base local (tarea 9.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function respuesta(cuerpo: unknown, ok = true): Response {
    return { ok, status: ok ? 200 : 500, json: async () => cuerpo } as unknown as Response
  }

  it('pide GET /api/v1/version y guarda la mínima en meta', async () => {
    const pedir = vi.fn(async () => respuesta({ version: '1.4.0', app_version_minima: '1.3.0' }))
    vi.stubGlobal('fetch', pedir)

    await actualizarVersionMinima()

    expect(String(pedir.mock.calls[0]?.[0])).toBe('/api/v1/version')
    expect((await baseLocal.meta.get(CLAVE_VERSION_MINIMA))?.valor).toBe('1.3.0')
  })

  it('sin señal o con error vale la última conocida; una mínima nula la borra', async () => {
    await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor: '1.3.0' })

    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('sin red'))))
    await actualizarVersionMinima()
    expect((await baseLocal.meta.get(CLAVE_VERSION_MINIMA))?.valor).toBe('1.3.0')

    vi.stubGlobal('fetch', vi.fn(async () => respuesta({}, false)))
    await actualizarVersionMinima()
    expect((await baseLocal.meta.get(CLAVE_VERSION_MINIMA))?.valor).toBe('1.3.0')

    vi.stubGlobal('fetch', vi.fn(async () => respuesta({ version: '1.4.0', app_version_minima: null })))
    await actualizarVersionMinima()
    expect(await baseLocal.meta.get(CLAVE_VERSION_MINIMA)).toBeUndefined()
  })

  it('la venta se bloquea según la última mínima guardada y la versión de la compilación', async () => {
    expect(await ventaBloqueadaPorVersion('1.2.0')).toBe(false)
    await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor: '1.3.0' })
    expect(await ventaBloqueadaPorVersion('1.2.0')).toBe(true)
    expect(await ventaBloqueadaPorVersion('1.3.0')).toBe(false)
    expect(await ventaBloqueadaPorVersion('dev')).toBe(false)
  })
})

describe('la sincronización pide la mínima y envía la cola igual (tarea 9.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
    vi.doUnmock('../../../src/sync/clienteLote')
  })

  it('al empezar el ciclo guarda la mínima y, aunque la app esté por debajo, la cola se envía', async () => {
    const candados = instalarCandadosDePrueba()
    vi.doMock('../../../src/sync/clienteLote', () => ({
      enviarLote: vi.fn(async (comandos: { operation_id: string }[]) => ({
        tipo: 'ok',
        corte: false,
        resultados: comandos.map((c) => ({ operation_id: c.operation_id, estado: 'ACEPTADO', resultado: null, error_codigo: null })),
      })),
    }))
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ version: '1.4.0', app_version_minima: '9.0.0' }) })),
    )
    const { crearSincronizador } = await import('../../../src/sync/sincronizar')
    const { baseLocal: base } = await import('../../../src/lib/dispositivo/db')
    await sembrarComando(comandoDePrueba(1))

    const resultado = await crearSincronizador().sincronizar({ usuarioId: 'u1', dispositivoId: 'd1', origen: 'manual' })

    expect(resultado).toEqual({ tipo: 'completa', enviadas: 1 })
    expect((await base.meta.get(CLAVE_VERSION_MINIMA))?.valor).toBe('9.0.0')
    expect(await ventaBloqueadaPorVersion('1.2.0')).toBe(true)
    candados.restaurar()
  })
})
