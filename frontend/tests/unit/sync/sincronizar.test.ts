import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import type { ResultadoDeLote } from '../../../src/sync/clienteLote'
import {
  CLAVE_ULTIMA_SINCRONIZACION,
  CLAVE_ULTIMO_ERROR_SYNC,
  crearSincronizador,
} from '../../../src/sync/sincronizar'
import { instalarCandadosDePrueba, type CandadosDePrueba } from '../utils/candadosDePrueba'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'

vi.mock('../../../src/sync/clienteLote', () => ({ enviarLote: vi.fn() }))

import { enviarLote } from '../../../src/sync/clienteLote'

/**
 * Change 22b, tareas 4.1 y 4.2 (spec `sync/motor-de-sincronizacion`, «El teléfono envía solo la
 * cola propia, en orden y por lotes», «Los cortes se reintentan con espera exponencial» y «Una
 * sola sincronización a la vez en el teléfono»; `design.md` D1, D2, D3, D5, D6; cita SYN-03,
 * `02` §13.3).
 */
const enviar = vi.mocked(enviarLote)
const AHORA = new Date('2026-11-01T12:00:00.000Z')
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

function nuevo(ahora: () => Date = () => AHORA) {
  return crearSincronizador({ ahora, azar: () => 0.5 })
}

async function estados(): Promise<string[]> {
  return (await baseLocal.cola.orderBy('secuencia').toArray()).map((c) => c.estado)
}

async function meta(clave: string): Promise<string | undefined> {
  return (await baseLocal.meta.get(clave))?.valor
}

describe('ciclo de sincronización (tarea 4.1)', () => {
  let candados: CandadosDePrueba
  beforeEach(async () => {
    candados = instalarCandadosDePrueba()
    enviar.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    candados.restaurar()
  })

  it('con el candado tomado envía lotes hasta vaciar la cola propia, aplica cada respuesta y guarda el éxito', async () => {
    for (let i = 1; i <= 120; i += 1) await sembrarComando(comandoDePrueba(i))
    await sembrarComando(comandoDePrueba(500, { usuarioId: 'otro' }))
    aceptarTodo()

    const resultado = await nuevo().sincronizar({ ...ENTRADA, origen: 'manual' })

    expect(resultado).toEqual({ tipo: 'completa', enviadas: 120 })
    expect(enviar.mock.calls.map(([lote]) => lote.length)).toEqual([50, 50, 20])
    expect(candados.pedidos).toEqual(['distribuidora:sync'])
    const e = await estados()
    expect(e.filter((x) => x === 'ACEPTADO')).toHaveLength(120)
    expect(e.filter((x) => x === 'PENDIENTE')).toHaveLength(1) // la del otro usuario
    expect(await meta(CLAVE_ULTIMA_SINCRONIZACION)).toBe(AHORA.toISOString())
    expect(await meta(CLAVE_ULTIMO_ERROR_SYNC)).toBeUndefined()
  })

  it('con la cola vacía no envía lote y igual es una sincronización exitosa con su hora', async () => {
    aceptarTodo()

    expect(await nuevo().sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'completa', enviadas: 0 })
    expect(enviar).not.toHaveBeenCalled()
    expect(await meta(CLAVE_ULTIMA_SINCRONIZACION)).toBe(AHORA.toISOString())
  })

  it('corta ante un transitorio dejando el resto pendiente; guarda el error y no cambia la última sincronización', async () => {
    for (let i = 1; i <= 60; i += 1) await sembrarComando(comandoDePrueba(i))
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SINCRONIZACION, valor: 'ayer' })
    enviar.mockResolvedValueOnce({ tipo: 'transitorio' })

    const resultado = await nuevo().sincronizar({ ...ENTRADA, origen: 'manual' })

    expect(resultado).toEqual({ tipo: 'transitorio' })
    expect(enviar).toHaveBeenCalledTimes(1)
    expect((await estados()).every((e) => e === 'PENDIENTE')).toBe(true)
    expect(await meta(CLAVE_ULTIMA_SINCRONIZACION)).toBe('ayer')
    expect(JSON.parse((await meta(CLAVE_ULTIMO_ERROR_SYNC)) ?? '{}')).toMatchObject({ tipo: 'transitorio' })
  })

  it('un ítem ERROR_TRANSITORIO en la respuesta aplica lo demás, corta y deja ese ítem pendiente', async () => {
    for (let i = 1; i <= 60; i += 1) await sembrarComando(comandoDePrueba(i))
    const respuesta: ResultadoDeLote = {
      tipo: 'ok',
      corte: true,
      resultados: [
        { operation_id: 'op-1', estado: 'ACEPTADO', resultado: null, error_codigo: null },
        { operation_id: 'op-2', estado: 'ERROR_TRANSITORIO', resultado: null, error_codigo: null },
      ],
    }
    enviar.mockResolvedValueOnce(respuesta)

    expect(await nuevo().sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'transitorio' })

    expect(enviar).toHaveBeenCalledTimes(1)
    expect((await estados()).slice(0, 3)).toEqual(['ACEPTADO', 'PENDIENTE', 'PENDIENTE'])
  })

  it('sesión vencida y error del pedido guardan el error con su tipo y código y no programan espera', async () => {
    await sembrarComando(comandoDePrueba(1))
    const motor = nuevo()
    enviar.mockResolvedValueOnce({ tipo: 'sesion_vencida' })
    expect(await motor.sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'sesion_vencida' })
    expect(JSON.parse((await meta(CLAVE_ULTIMO_ERROR_SYNC)) ?? '{}')).toMatchObject({ tipo: 'sesion_vencida' })
    expect(motor.estadoDeEspera().hasta).toBeNull()

    enviar.mockResolvedValueOnce({ tipo: 'error_pedido', estado: 403, codigo: 'COLA_AJENA' })
    expect(await motor.sincronizar({ ...ENTRADA, origen: 'venta' })).toEqual({
      tipo: 'error_pedido',
      estado: 403,
      codigo: 'COLA_AJENA',
    })
    expect(JSON.parse((await meta(CLAVE_ULTIMO_ERROR_SYNC)) ?? '{}')).toMatchObject({
      tipo: 'error_pedido',
      codigo: 'COLA_AJENA',
    })
    expect(motor.estadoDeEspera().hasta).toBeNull()
  })

  it('un éxito posterior borra el último error', async () => {
    await sembrarComando(comandoDePrueba(1))
    const motor = nuevo()
    enviar.mockResolvedValueOnce({ tipo: 'transitorio' })
    await motor.sincronizar({ ...ENTRADA, origen: 'manual' })
    expect(await meta(CLAVE_ULTIMO_ERROR_SYNC)).toBeDefined()

    aceptarTodo()
    await motor.sincronizar({ ...ENTRADA, origen: 'manual' })

    expect(await meta(CLAVE_ULTIMO_ERROR_SYNC)).toBeUndefined()
  })
})

describe('espera exponencial en el ciclo (tarea 4.1; D5, D6 = B)', () => {
  let candados: CandadosDePrueba
  beforeEach(async () => {
    candados = instalarCandadosDePrueba()
    enviar.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarComando(comandoDePrueba(1))
  })
  afterEach(() => {
    candados.restaurar()
  })

  it('tras un transitorio, venta/periódico/arranque respetan la espera: no envían antes de que venza', async () => {
    let reloj = AHORA.getTime()
    const motor = nuevo(() => new Date(reloj))
    enviar.mockResolvedValueOnce({ tipo: 'transitorio' })
    await motor.sincronizar({ ...ENTRADA, origen: 'periodico' })
    enviar.mockClear()

    for (const origen of ['venta', 'periodico', 'arranque'] as const) {
      expect(await motor.sincronizar({ ...ENTRADA, origen })).toEqual({ tipo: 'en_espera' })
    }
    expect(enviar).not.toHaveBeenCalled()

    reloj += 5_001
    aceptarTodo()
    expect(await motor.sincronizar({ ...ENTRADA, origen: 'periodico' })).toEqual({ tipo: 'completa', enviadas: 1 })
  })

  it.each(['manual', 'online', 'primer_plano'] as const)(
    '%s vuelve la espera a cero y envía en el momento, aunque la espera siga vigente',
    async (origen) => {
      const motor = nuevo()
      enviar.mockResolvedValueOnce({ tipo: 'transitorio' })
      await motor.sincronizar({ ...ENTRADA, origen: 'periodico' })
      expect(motor.estadoDeEspera().fallos).toBe(1)

      aceptarTodo()
      expect(await motor.sincronizar({ ...ENTRADA, origen })).toEqual({ tipo: 'completa', enviadas: 1 })
      expect(motor.estadoDeEspera()).toEqual({ fallos: 0, hasta: null })
    },
  )

  it('los fallos seguidos suben la espera (5 s, luego 10 s) y reiniciarEspera la limpia', async () => {
    let reloj = AHORA.getTime()
    const motor = nuevo(() => new Date(reloj))
    enviar.mockResolvedValue({ tipo: 'transitorio' })

    await motor.sincronizar({ ...ENTRADA, origen: 'periodico' })
    expect(motor.estadoDeEspera()).toEqual({ fallos: 1, hasta: reloj + 5_000 })
    reloj += 5_001
    await motor.sincronizar({ ...ENTRADA, origen: 'periodico' })
    expect(motor.estadoDeEspera()).toEqual({ fallos: 2, hasta: reloj + 10_000 })

    motor.reiniciarEspera()
    expect(motor.estadoDeEspera()).toEqual({ fallos: 0, hasta: null })
  })
})

describe('una sola sincronización a la vez (tarea 4.2; D2; `02` §13.3)', () => {
  let candados: CandadosDePrueba
  beforeEach(async () => {
    candados = instalarCandadosDePrueba()
    enviar.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    candados.restaurar()
  })

  it('si otra «pestaña» tiene el candado, no envía e informa «otra pestaña»', async () => {
    await sembrarComando(comandoDePrueba(1))
    aceptarTodo()
    let soltar!: () => void
    const tomado = new Promise<void>((resolver) => {
      soltar = resolver
    })
    const otra = navigator.locks.request('distribuidora:sync', () => tomado)
    await new Promise((r) => setTimeout(r, 0))

    expect(await nuevo().sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'otra_pestana' })
    expect(enviar).not.toHaveBeenCalled()
    expect((await estados())[0]).toBe('PENDIENTE')

    soltar()
    await otra
    expect(await nuevo().sincronizar({ ...ENTRADA, origen: 'manual' })).toEqual({ tipo: 'completa', enviadas: 1 })
  })

  it('un disparador durante el envío produce UNA vuelta más al terminar (varios no apilan)', async () => {
    await sembrarComando(comandoDePrueba(1))
    let liberarPrimero!: () => void
    enviar.mockImplementationOnce(async (comandos) => {
      await new Promise<void>((resolver) => {
        liberarPrimero = resolver
      })
      return {
        tipo: 'ok',
        corte: false,
        resultados: comandos.map((c) => ({ operation_id: c.operation_id, estado: 'ACEPTADO', resultado: null, error_codigo: null })),
      }
    })
    aceptarTodo()
    const motor = nuevo()

    const primera = motor.sincronizar({ ...ENTRADA, origen: 'manual' })
    await vi.waitFor(() => expect(enviar).toHaveBeenCalledTimes(1))
    // Llegan una venta nueva y tres disparadores mientras se envía.
    await sembrarComando(comandoDePrueba(2))
    const durante = await Promise.all([
      motor.sincronizar({ ...ENTRADA, origen: 'venta' }),
      motor.sincronizar({ ...ENTRADA, origen: 'primer_plano' }),
      motor.sincronizar({ ...ENTRADA, origen: 'periodico' }),
    ])
    expect(durante).toEqual([{ tipo: 'repetira' }, { tipo: 'repetira' }, { tipo: 'repetira' }])
    liberarPrimero()

    expect(await primera).toEqual({ tipo: 'completa', enviadas: 2 })
    expect(enviar).toHaveBeenCalledTimes(2) // el envío original más UNA vuelta
    expect((await estados()).every((e) => e === 'ACEPTADO')).toBe(true)
  })

  it('un disparador durante el envío no apila vueltas si el envío falla (corte)', async () => {
    await sembrarComando(comandoDePrueba(1))
    let liberar!: () => void
    enviar.mockImplementationOnce(async () => {
      await new Promise<void>((resolver) => {
        liberar = resolver
      })
      return { tipo: 'transitorio' }
    })
    const motor = nuevo()

    const primera = motor.sincronizar({ ...ENTRADA, origen: 'manual' })
    await vi.waitFor(() => expect(enviar).toHaveBeenCalledTimes(1))
    await motor.sincronizar({ ...ENTRADA, origen: 'venta' })
    liberar()

    expect(await primera).toEqual({ tipo: 'transitorio' })
    expect(enviar).toHaveBeenCalledTimes(1)
  })
})
