import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../src/lib/api/httpClient', () => ({ apiFetch: vi.fn() }))

import { sincronizarAlEntrar } from '../../../src/areas/ruta/sesion/entrada'
import { apiFetch } from '../../../src/lib/api/httpClient'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { actualizarDatos } from '../../../src/sync/actualizarDatos'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { aplicarResultados } from '../../../src/sync/aplicarResultados'
import {
  CLAVE_JORNADA_NO_ABIERTA,
  consultarEstadoDeJornada,
  leerJornadaNoAbierta,
  marcarJornadaNoAbierta,
} from '../../../src/sync/estadoDeJornada'
import { bootstrapDePrueba, ID } from '../utils/bootstrapDePrueba'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'

/**
 * Change 22d, tarea 9.1 (spec `sync/motor-de-sincronizacion`, «Con señal, el teléfono se entera de
 * que su jornada ya no está abierta», sus siete escenarios; `design.md` D8; cita RUT-03, RUT-09,
 * SYN-07, SYN-09, INV-06). La jornada de la sesión de prueba es `ID(2)`.
 */
const pedir = vi.mocked(apiFetch)
const J1 = ID(2)
const AHORA = new Date('2026-11-03T12:00:00.000Z')
const OTRA_HORA = new Date('2026-11-03T12:05:00.000Z')

function responder(estado: number, cuerpo: unknown = {}): Response {
  return new Response(JSON.stringify(cuerpo), { status: estado, headers: { 'Content-Type': 'application/json' } })
}

async function guardado(): Promise<unknown> {
  const fila = await baseLocal.meta.get(CLAVE_JORNADA_NO_ABIERTA)
  return fila === undefined ? undefined : JSON.parse(fila.valor)
}

describe('estado de la jornada del teléfono (change 22d, tarea 9.1)', () => {
  beforeEach(async () => {
    pedir.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
  })

  describe('consultarEstadoDeJornada: GET /stock/jornadas/{id} de la sesión (D8, RUT-09)', () => {
    it.each(['LIBERADA', 'EN_RENDICION', 'CERRADA'])('%s se guarda con la jornada y el momento', async (estado) => {
      pedir.mockResolvedValue(responder(200, { id: J1, estado }))

      await consultarEstadoDeJornada(AHORA)

      expect(pedir).toHaveBeenCalledWith(`/stock/jornadas/${J1}`)
      expect(await guardado()).toEqual({ jornada_id: J1, estado, en: AHORA.toISOString() })
      expect(await leerJornadaNoAbierta()).toEqual({ jornada_id: J1, estado, en: AHORA.toISOString() })
    })

    it('ABIERTA no cambia nada', async () => {
      pedir.mockResolvedValue(responder(200, { id: J1, estado: 'ABIERTA' }))

      await consultarEstadoDeJornada(AHORA)

      expect(await guardado()).toBeUndefined()
      expect(await leerJornadaNoAbierta()).toBeNull()
    })

    it('ABIERTA tampoco borra lo que ya estaba guardado (no se «reabre» sola una jornada)', async () => {
      await marcarJornadaNoAbierta(J1, 'LIBERADA', AHORA)
      pedir.mockResolvedValue(responder(200, { id: J1, estado: 'ABIERTA' }))

      await consultarEstadoDeJornada(OTRA_HORA)

      expect(await guardado()).toEqual({ jornada_id: J1, estado: 'LIBERADA', en: AHORA.toISOString() })
    })

    it('sin red, 403, 404, 500 o respuesta ilegible no cambian nada y no lanzan (RUT-09, CRE-08)', async () => {
      pedir.mockRejectedValueOnce(new TypeError('Failed to fetch'))
      await consultarEstadoDeJornada(AHORA)
      for (const estado of [403, 404, 500]) {
        pedir.mockResolvedValueOnce(responder(estado, { codigo: 'X' }))
        await consultarEstadoDeJornada(AHORA)
      }
      pedir.mockResolvedValueOnce(new Response('no es json', { status: 200 }))
      await consultarEstadoDeJornada(AHORA)

      expect(pedir).toHaveBeenCalledTimes(5)
      expect(await guardado()).toBeUndefined()
    })

    it('sin sesión local no consulta', async () => {
      await baseLocal.sesion.clear()

      await consultarEstadoDeJornada(AHORA)

      expect(pedir).not.toHaveBeenCalled()
    })

    it('doble consulta: la misma respuesta otra vez no cambia lo guardado, ni el momento (INV-06)', async () => {
      pedir.mockResolvedValue(responder(200, { id: J1, estado: 'LIBERADA' }))

      await consultarEstadoDeJornada(AHORA)
      await consultarEstadoDeJornada(OTRA_HORA)

      expect(await guardado()).toEqual({ jornada_id: J1, estado: 'LIBERADA', en: AHORA.toISOString() })
    })

    it('un estado más preciso reemplaza al anterior (de «desconocido» a LIBERADA)', async () => {
      await marcarJornadaNoAbierta(J1, 'DESCONOCIDO', AHORA)
      pedir.mockResolvedValue(responder(200, { id: J1, estado: 'LIBERADA' }))

      await consultarEstadoDeJornada(OTRA_HORA)

      expect(await guardado()).toEqual({ jornada_id: J1, estado: 'LIBERADA', en: OTRA_HORA.toISOString() })
    })
  })

  describe('marcarJornadaNoAbierta y leerJornadaNoAbierta', () => {
    it('«desconocido» no pisa un estado conocido', async () => {
      await marcarJornadaNoAbierta(J1, 'CERRADA', AHORA)
      await marcarJornadaNoAbierta(J1, 'DESCONOCIDO', OTRA_HORA)

      expect(await leerJornadaNoAbierta()).toEqual({ jornada_id: J1, estado: 'CERRADA', en: AHORA.toISOString() })
    })

    it('lo guardado para una jornada que no es la de la sesión se ignora al leer y no se guarda al marcar', async () => {
      await marcarJornadaNoAbierta(ID(99), 'LIBERADA', AHORA)
      expect(await guardado()).toBeUndefined()

      await baseLocal.meta.put({
        clave: CLAVE_JORNADA_NO_ABIERTA,
        valor: JSON.stringify({ jornada_id: ID(99), estado: 'LIBERADA', en: AHORA.toISOString() }),
      })
      expect(await leerJornadaNoAbierta()).toBeNull()
    })

    it('un valor ilegible en meta se lee como «sin dato»', async () => {
      await baseLocal.meta.put({ clave: CLAVE_JORNADA_NO_ABIERTA, valor: '{no es json' })
      expect(await leerJornadaNoAbierta()).toBeNull()
    })
  })

  describe('«Actualizar datos» y la entrada con señal', () => {
    it('JORNADA_REQUERIDA de «Actualizar datos» guarda «desconocido» (RUT-03, SYN-11)', async () => {
      pedir.mockResolvedValue(responder(409, { codigo: 'JORNADA_REQUERIDA' }))

      expect(await actualizarDatos()).toBe('sin_jornada')

      expect(await leerJornadaNoAbierta()).toMatchObject({ jornada_id: J1, estado: 'DESCONOCIDO' })
    })

    it('«Actualizar datos» con éxito no guarda ni borra nada de la jornada', async () => {
      await marcarJornadaNoAbierta(J1, 'LIBERADA', AHORA)
      pedir.mockResolvedValue(responder(200, bootstrapDePrueba({ generado: '2026-11-03T13:00:00Z' })))

      expect(await actualizarDatos()).toBe('actualizados')

      expect(await leerJornadaNoAbierta()).toMatchObject({ estado: 'LIBERADA' })
    })

    it('sin jornada abierta al entrar guarda «desconocido»; con la jornada en rendición, ese estado', async () => {
      pedir.mockResolvedValue(responder(404, { codigo: 'RECURSO_NO_ENCONTRADO' }))
      expect(await sincronizarAlEntrar()).toEqual({ tipo: 'sin_jornada' })
      expect(await leerJornadaNoAbierta()).toMatchObject({ jornada_id: J1, estado: 'DESCONOCIDO' })

      await baseLocal.meta.delete(CLAVE_JORNADA_NO_ABIERTA)
      pedir.mockResolvedValue(responder(200, { id: J1, estado: 'EN_RENDICION' }))
      expect(await sincronizarAlEntrar()).toEqual({ tipo: 'sin_jornada' })
      expect(await leerJornadaNoAbierta()).toMatchObject({ jornada_id: J1, estado: 'EN_RENDICION' })
    })

    it('si la jornada no cerrada del servidor es otra que la local, la local queda «desconocido»', async () => {
      pedir.mockResolvedValue(responder(200, { id: ID(60), estado: 'EN_RENDICION' }))

      expect(await sincronizarAlEntrar()).toEqual({ tipo: 'sin_jornada' })

      expect(await leerJornadaNoAbierta()).toMatchObject({ jornada_id: J1, estado: 'DESCONOCIDO' })
    })

    it('con la jornada abierta al entrar no guarda nada', async () => {
      pedir.mockResolvedValue(responder(200, { id: J1, estado: 'ABIERTA' }))

      expect(await sincronizarAlEntrar()).toEqual({ tipo: 'al_dia' })

      expect(await guardado()).toBeUndefined()
    })
  })

  describe('un resultado del lote con JORNADA_LIBERADA (SYN-07, RUT-09)', () => {
    const observacion = { codigo: 'JORNADA_LIBERADA', operacion_tipo: 'VENTA', operacion_id: ID(500), detalle: null }

    it('guarda LIBERADA para la jornada del comando', async () => {
      await sembrarComando(comandoDePrueba(1, { jornadaId: J1 }))

      await aplicarResultados(
        [{ operation_id: 'op-1', estado: 'ACEPTADO_CON_OBSERVACIONES', resultado: null, error_codigo: null, observaciones: [observacion] }],
        AHORA,
      )

      expect(await leerJornadaNoAbierta()).toEqual({ jornada_id: J1, estado: 'LIBERADA', en: AHORA.toISOString() })
    })

    it('otra observación no marca nada; una jornada que no es la de la sesión tampoco', async () => {
      await sembrarComando(comandoDePrueba(1, { jornadaId: J1 }))
      await sembrarComando(comandoDePrueba(2, { jornadaId: ID(77) }))

      await aplicarResultados(
        [
          {
            operation_id: 'op-1',
            estado: 'ACEPTADO_CON_OBSERVACIONES',
            resultado: null,
            error_codigo: null,
            observaciones: [{ ...observacion, codigo: 'PERMISO_REVOCADO' }],
          },
          { operation_id: 'op-2', estado: 'ACEPTADO_CON_OBSERVACIONES', resultado: null, error_codigo: null, observaciones: [observacion] },
        ],
        AHORA,
      )

      expect(await guardado()).toBeUndefined()
    })

    it('reenviar el mismo resultado no cambia lo guardado (INV-06)', async () => {
      await sembrarComando(comandoDePrueba(1, { jornadaId: J1 }))
      const item = {
        operation_id: 'op-1',
        estado: 'ACEPTADO_CON_OBSERVACIONES',
        resultado: null,
        error_codigo: null,
        observaciones: [observacion],
      }

      await aplicarResultados([item], AHORA)
      await aplicarResultados([item], OTRA_HORA)

      expect(await guardado()).toEqual({ jornada_id: J1, estado: 'LIBERADA', en: AHORA.toISOString() })
    })
  })

  describe('el bootstrap de otra jornada borra la marca (RUT-03)', () => {
    it('al abrir la jornada J2 y aplicar su bootstrap, el teléfono ya no la considera no abierta', async () => {
      await marcarJornadaNoAbierta(J1, 'LIBERADA', AHORA)
      const bootstrap = bootstrapDePrueba({ generado: '2026-11-03T14:00:00Z' })
      bootstrap.sesion.jornada = { ...bootstrap.sesion.jornada, id: ID(50) }

      await aplicarBootstrap(bootstrap)

      expect(await guardado()).toBeUndefined()
      expect(await leerJornadaNoAbierta()).toBeNull()
    })

    it('un bootstrap de la misma jornada deja la marca como estaba', async () => {
      await marcarJornadaNoAbierta(J1, 'LIBERADA', AHORA)

      await aplicarBootstrap(bootstrapDePrueba({ generado: '2026-11-03T14:00:00Z' }))

      expect(await leerJornadaNoAbierta()).toEqual({ jornada_id: J1, estado: 'LIBERADA', en: AHORA.toISOString() })
    })
  })
})
