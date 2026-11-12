import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import {
  dispararTrasVenta,
  estadoDeSincronizacion,
  iniciarDisparadores,
  sincronizarAPedido,
  type Disparadores,
} from '../../../src/sync/disparadores'
import { crearSincronizador, type OrigenDeSincronizacion, type ResultadoDeSincronizacion } from '../../../src/sync/sincronizar'
import { instalarCandadosDePrueba, type CandadosDePrueba } from '../utils/candadosDePrueba'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'

vi.mock('../../../src/sync/clienteLote', () => ({ enviarLote: vi.fn() }))

import { enviarLote } from '../../../src/sync/clienteLote'

/**
 * Change 22b, tareas 8.1 y 8.2 (spec `sync/motor-de-sincronizacion`, «La sincronización se dispara
 * sola y a pedido»; `design.md` D6 = B, D2, D5; cita `02` §13.3, SEG-03, ADR-064).
 */
const enviar = vi.mocked(enviarLote)
const ENTRADA = { usuarioId: 'u1', dispositivoId: 'd1' } as const

function aceptarTodo(): void {
  enviar.mockImplementation(async (comandos) => ({
    tipo: 'ok',
    corte: false,
    resultados: comandos.map((c) => ({
      operation_id: c.operation_id,
      estado: 'ACEPTADO',
      resultado: null,
      error_codigo: null,
    })),
  }))
}

function conectado(valor: boolean): void {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

function visibilidad(valor: 'visible' | 'hidden'): void {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => valor })
  document.dispatchEvent(new Event('visibilitychange'))
}

/** Sincronizador de espía: registra el origen de cada disparo. */
function espia() {
  const origenes: OrigenDeSincronizacion[] = []
  let responder: () => Promise<ResultadoDeSincronizacion> = async () => ({ tipo: 'completa', enviadas: 0 })
  const sincronizar = vi.fn(async (entrada: { origen: OrigenDeSincronizacion }) => {
    origenes.push(entrada.origen)
    return responder()
  })
  return {
    origenes,
    sincronizador: { sincronizar, reiniciarEspera: vi.fn(), estadoDeEspera: vi.fn() },
    responder: (nuevo: () => Promise<ResultadoDeSincronizacion>) => {
      responder = nuevo
    },
  }
}

async function vaciarPromesas(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

describe('disparadores con la sesión desbloqueada (tarea 8.1)', () => {
  let activos: Disparadores | null = null
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    conectado(true)
  })
  afterEach(() => {
    activos?.detener()
    activos = null
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('sincroniza al empezar (al desbloquear o terminar el login), con «online» y con «Sincronizar»', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque'])

    window.dispatchEvent(new Event('online'))
    await vaciarPromesas()
    await sincronizarAPedido()
    expect(origenes).toEqual(['arranque', 'online', 'manual'])
  })

  it('sincroniza cada 2 minutos mientras está abierta, y no antes', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()

    await vi.advanceTimersByTimeAsync(119_999)
    expect(origenes).toEqual(['arranque'])
    await vi.advanceTimersByTimeAsync(1)
    expect(origenes).toEqual(['arranque', 'periodico'])
    await vi.advanceTimersByTimeAsync(120_000)
    expect(origenes).toEqual(['arranque', 'periodico', 'periodico'])
  })

  it('después de confirmar una venta sincroniza solo si hay conexión', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()

    conectado(false)
    dispararTrasVenta()
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque'])

    conectado(true)
    dispararTrasVenta()
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque', 'venta'])
  })

  it('«Sincronizar» sin conexión informa «sin señal» y no envía', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()

    conectado(false)
    expect(await sincronizarAPedido()).toEqual({ tipo: 'sin_senal' })
    expect(origenes).toEqual(['arranque'])
    expect(estadoDeSincronizacion().fase).toBe('sin_senal')
  })

  it('con la sesión bloqueada (disparadores detenidos) no envía ni por «online», ni por tiempo, ni a pedido', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()
    activos.detener()
    activos = null

    window.dispatchEvent(new Event('online'))
    await vi.advanceTimersByTimeAsync(240_000)
    dispararTrasVenta()
    expect(await sincronizarAPedido()).toEqual({ tipo: 'sin_sesion' })
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque'])
  })

  it('tras un transitorio respeta la espera para el periódico y la venta, y «online» la salta', async () => {
    const candados: CandadosDePrueba = instalarCandadosDePrueba()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('sin red'))))
    await sembrarComando(comandoDePrueba(1))
    enviar.mockReset()
    enviar.mockResolvedValue({ tipo: 'transitorio' })
    const real = crearSincronizador({ azar: () => 0.5 })
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador: real })
    await new Promise((r) => setTimeout(r, 30))
    expect(enviar).toHaveBeenCalledTimes(1)

    // Espera de 5 s: la venta y el periódico dentro de ese tiempo no envían.
    dispararTrasVenta()
    await new Promise((r) => setTimeout(r, 50))
    expect(enviar).toHaveBeenCalledTimes(1)

    // «online» vuelve la espera a cero y envía en el momento.
    window.dispatchEvent(new Event('online'))
    await new Promise((r) => setTimeout(r, 30))
    expect(enviar).toHaveBeenCalledTimes(2)
    candados.restaurar()
    vi.unstubAllGlobals()
  })
})

describe('vuelta a primer plano (tarea 8.2)', () => {
  let activos: Disparadores | null = null
  beforeEach(() => {
    conectado(true)
    visibilidad('visible')
  })
  afterEach(() => {
    activos?.detener()
    activos = null
    vi.restoreAllMocks()
  })

  it('«visible» con la sesión desbloqueada dispara; «hidden» no', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()

    visibilidad('hidden')
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque'])

    visibilidad('visible')
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque', 'primer_plano'])
  })

  it('con la sesión bloqueada o sin usuario local «visible» no dispara: el oyente se quita al detener', async () => {
    const { origenes, sincronizador } = espia()
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador })
    await vaciarPromesas()
    const quitar = vi.spyOn(document, 'removeEventListener')
    activos.detener()
    activos = null
    expect(quitar.mock.calls.map((c) => c[0])).toContain('visibilitychange')

    visibilidad('visible')
    await vaciarPromesas()
    expect(origenes).toEqual(['arranque'])
  })
})

describe('primer plano con el motor real (tarea 8.2)', () => {
  let candados: CandadosDePrueba
  let activos: Disparadores | null = null
  beforeEach(async () => {
    candados = instalarCandadosDePrueba()
    conectado(true)
    visibilidad('visible')
    enviar.mockReset()
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('sin red'))))
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    activos?.detener()
    activos = null
    candados.restaurar()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('durante un envío propio, varios disparadores (primer plano incluido) producen una sola vuelta más', async () => {
    await sembrarComando(comandoDePrueba(1))
    let liberar: () => void = () => undefined
    const bloqueo = new Promise<void>((r) => {
      liberar = r
    })
    let llamadas = 0
    enviar.mockImplementation(async (comandos) => {
      llamadas += 1
      if (llamadas === 1) await bloqueo
      return {
        tipo: 'ok',
        corte: false,
        resultados: comandos.map((c) => ({ operation_id: c.operation_id, estado: 'ACEPTADO', resultado: null, error_codigo: null })),
      }
    })
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador: crearSincronizador() })
    await vaciarPromesas()
    await new Promise((r) => setTimeout(r, 20))
    expect(estadoDeSincronizacion().fase).toBe('enviando')

    visibilidad('visible')
    window.dispatchEvent(new Event('online'))
    visibilidad('visible')
    await sembrarComando(comandoDePrueba(2))
    liberar()
    await new Promise((r) => setTimeout(r, 80))

    // Un solo lote con la venta 1 y, tras el repetir, un lote más con la 2 (no tres).
    expect(enviar).toHaveBeenCalledTimes(2)
    expect(estadoDeSincronizacion().fase).toBe('ocioso')
  })

  it('con otra «pestaña» sincronizando no envía y lo informa', async () => {
    await sembrarComando(comandoDePrueba(1))
    aceptarTodo()
    // La otra pestaña tiene el candado único.
    let soltar: () => void = () => undefined
    const tomado = new Promise<void>((r) => {
      soltar = r
    })
    void navigator.locks.request('distribuidora:sync', async () => {
      await tomado
    })

    activos = iniciarDisparadores({ ...ENTRADA, sincronizador: crearSincronizador() })
    await new Promise((r) => setTimeout(r, 30))
    visibilidad('visible')
    await new Promise((r) => setTimeout(r, 30))

    expect(enviar).not.toHaveBeenCalled()
    expect(estadoDeSincronizacion().fase).toBe('otra_pestana')
    soltar()
  })

  it('con una espera exponencial vigente, volver a primer plano la pone en cero y envía en el momento', async () => {
    await sembrarComando(comandoDePrueba(1))
    enviar.mockResolvedValueOnce({ tipo: 'transitorio' })
    const real = crearSincronizador({ azar: () => 0.5 })
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador: real })
    await new Promise((r) => setTimeout(r, 30))
    expect(enviar).toHaveBeenCalledTimes(1)
    expect(real.estadoDeEspera().fallos).toBeGreaterThan(0)

    aceptarTodo()
    dispararTrasVenta()
    await new Promise((r) => setTimeout(r, 30))
    expect(enviar).toHaveBeenCalledTimes(1) // la venta respeta la espera

    visibilidad('visible')
    await new Promise((r) => setTimeout(r, 50))
    expect(enviar).toHaveBeenCalledTimes(2)
    expect(real.estadoDeEspera().fallos).toBe(0)
  })

  it('«Sincronizando en otra pestaña» se apaga cuando esa pestaña escribe su éxito', async () => {
    const prueba = espia()
    prueba.responder(async () => ({ tipo: 'otra_pestana' }))
    activos = iniciarDisparadores({ ...ENTRADA, sincronizador: prueba.sincronizador })
    await new Promise((r) => setTimeout(r, 40))
    expect(estadoDeSincronizacion().fase).toBe('otra_pestana')

    await baseLocal.meta.put({ clave: 'ultima_sincronizacion', valor: '2026-11-01T12:00:00.000Z' })
    await new Promise((r) => setTimeout(r, 60))

    expect(estadoDeSincronizacion().fase).toBe('ocioso')
  })
})
