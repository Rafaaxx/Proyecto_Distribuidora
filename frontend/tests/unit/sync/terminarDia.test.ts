import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { aplicarResultados } from '../../../src/sync/aplicarResultados'
import { CLAVE_ULTIMA_SECUENCIA } from '../../../src/sync/confirmarVentaLocal'
import { CLAVE_JORNADA_NO_ABIERTA, leerJornadaNoAbierta, marcarJornadaNoAbierta } from '../../../src/sync/estadoDeJornada'
import { armarSobreDeEntrega } from '../../../src/sync/sobre'
import { contarPendientes } from '../../../src/sync/ventasPendientes'
import { terminarElDia } from '../../../src/sync/terminarDia'
import { bootstrapDePrueba, ID } from '../utils/bootstrapDePrueba'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'

/**
 * Change 24, tarea 14.1 (spec `ruta/area-de-ruta`, «Terminar el día sin señal», «Falla al terminar
 * el día» y «Doble toque»; `design.md` D1, D10; cita **INV-01**, INV-06, RUT-05, SYN-03). La
 * jornada de la sesión de prueba es `ID(2)`; el vendedor, `ID(1)`.
 */
const AHORA = new Date('2026-11-04T18:00:00.000Z')
const J1 = ID(2)

function entrada(operationId: string) {
  return { operationId, usuarioId: ID(1), dispositivoId: 'disp-1', ahora: AHORA, appVersion: '1.0.0' }
}

async function estadoLocal() {
  return {
    cola: await baseLocal.cola.count(),
    ultimaSecuencia: (await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor,
    marca: (await baseLocal.meta.get(CLAVE_JORNADA_NO_ABIERTA))?.valor,
  }
}

describe('armarSobreDeEntrega (D1; SYN-01)', () => {
  it('es un JORNADA_ENTREGAR v1 OFFLINE con contenido vacío y la jornada del sobre', () => {
    const sobre = armarSobreDeEntrega({
      operationId: 'op-e',
      usuarioId: 'u1',
      dispositivoId: 'd1',
      jornadaId: 'j1',
      occurredAt: AHORA,
      secuencia: 4,
      appVersion: '1.0.0',
    })
    expect(sobre).toEqual({
      operation_id: 'op-e',
      tipo: 'JORNADA_ENTREGAR',
      version: 1,
      modo: 'OFFLINE',
      usuario_id: 'u1',
      dispositivo_id: 'd1',
      jornada_id: 'j1',
      occurred_at: AHORA.toISOString(),
      secuencia: 4,
      app_version: '1.0.0',
      contenido: {},
    })
  })
})

describe('terminar el día es una sola transacción local (change 24, tarea 14.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sin señal y sin nada pendiente encola la entrega con la secuencia 1 y guarda la marca ENTREGADA (RUT-05, SYN-03)', async () => {
    const r = await terminarElDia(entrada('op-e1'))

    expect(r.repetida).toBe(false)
    expect(r.comando).toMatchObject({ secuencia: 1, operation_id: 'op-e1', estado: 'PENDIENTE' })
    expect(r.comando.sobre).toMatchObject({
      tipo: 'JORNADA_ENTREGAR',
      version: 1,
      modo: 'OFFLINE',
      secuencia: 1,
      jornada_id: J1,
      usuario_id: ID(1),
      dispositivo_id: 'disp-1',
    })
    expect(await baseLocal.cola.get(1)).toEqual(r.comando)
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBe('1')
    expect(await leerJornadaNoAbierta()).toEqual({ jornada_id: J1, estado: 'ENTREGADA', en: AHORA.toISOString() })
  })

  it('va detrás de lo ya encolado: la secuencia siguiente a la última (SYN-03)', async () => {
    await sembrarComando(comandoDePrueba(1, { jornadaId: J1, usuarioId: ID(1) }))
    await sembrarComando(comandoDePrueba(2, { jornadaId: J1, usuarioId: ID(1) }))
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SECUENCIA, valor: '2' })

    const r = await terminarElDia(entrada('op-e2'))

    expect(r.comando.secuencia).toBe(3)
    expect(r.comando.sobre.secuencia).toBe(3)
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBe('3')
    expect((await baseLocal.cola.toArray()).map((c) => c.secuencia)).toEqual([1, 2, 3])
  })

  it('la entrega no cuenta como venta sin enviar (la cola cuenta solo ventas, anulaciones y cobranzas)', async () => {
    await terminarElDia(entrada('op-e3'))

    expect(await contarPendientes(ID(1))).toEqual({ ventas: 0, anulaciones: 0, cobranzas: 0 })
  })

  it('INV-01: una falla al escribir la cola no deja marca, ni comando, ni avance de la secuencia', async () => {
    vi.spyOn(baseLocal.cola, 'add').mockRejectedValueOnce(new Error('disco lleno'))
    const antes = await estadoLocal()

    await expect(terminarElDia(entrada('op-e4'))).rejects.toThrow('disco lleno')

    expect(await estadoLocal()).toEqual(antes)
    expect(await leerJornadaNoAbierta()).toBeNull()
  })

  it('INV-01: una falla al guardar la marca deshace también el comando encolado', async () => {
    const original = baseLocal.meta.put.bind(baseLocal.meta)
    vi.spyOn(baseLocal.meta, 'put').mockImplementation(async (valor, ...resto) => {
      if (valor.clave === CLAVE_JORNADA_NO_ABIERTA) throw new Error('sin cuota')
      return original(valor, ...resto)
    })

    await expect(terminarElDia(entrada('op-e5'))).rejects.toThrow('sin cuota')

    expect(await baseLocal.cola.count()).toBe(0)
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBeUndefined()
  })

  it('doble toque: reconfirmar no encola otra entrega y devuelve la existente (INV-06)', async () => {
    const primera = await terminarElDia(entrada('op-e6'))
    const segunda = await terminarElDia(entrada('op-e6-otro'))

    expect(segunda.repetida).toBe(true)
    expect(segunda.comando).toEqual(primera.comando)
    expect(await baseLocal.cola.count()).toBe(1)
    expect((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor).toBe('1')
  })

  it('sin sesión local no hay día que terminar', async () => {
    await baseLocal.sesion.clear()

    await expect(terminarElDia(entrada('op-e7'))).rejects.toThrow(/sesión/)
    expect(await baseLocal.cola.count()).toBe(0)
  })

  it('el resultado del servidor se escribe en la cola y la marca sigue (SYN-09, RUT-05)', async () => {
    const { comando } = await terminarElDia(entrada('op-e8'))

    await aplicarResultados(
      [{ operation_id: comando.operation_id, estado: 'ACEPTADO', resultado: { jornada_id: J1 }, error_codigo: null }],
      new Date('2026-11-04T18:05:00.000Z'),
    )

    expect(await baseLocal.cola.get(1)).toMatchObject({ estado: 'ACEPTADO', resultado_en: '2026-11-04T18:05:00.000Z' })
    expect((await leerJornadaNoAbierta())?.estado).toBe('ENTREGADA')
  })

  it('un rechazo de la entrega queda con su código en la cola y no borra la marca (SYN-06)', async () => {
    const { comando } = await terminarElDia(entrada('op-e9'))

    await aplicarResultados(
      [{ operation_id: comando.operation_id, estado: 'RECHAZADO', resultado: null, error_codigo: 'JORNADA_YA_ENTREGADA' }],
      new Date('2026-11-04T18:05:00.000Z'),
    )

    expect(await baseLocal.cola.get(1)).toMatchObject({ estado: 'RECHAZADO', error_codigo: 'JORNADA_YA_ENTREGADA' })
    expect((await leerJornadaNoAbierta())?.estado).toBe('ENTREGADA')
  })
})

describe('la marca ENTREGADA convive con lo que el servidor cuenta de la jornada (D10; RUT-05, SYN-09)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDePrueba())
  })

  it('sobrevive a la recarga: se lee de meta', async () => {
    await terminarElDia(entrada('op-m1'))

    const fila = await baseLocal.meta.get(CLAVE_JORNADA_NO_ABIERTA)
    expect(JSON.parse(fila?.valor ?? '{}')).toEqual({ jornada_id: J1, estado: 'ENTREGADA', en: AHORA.toISOString() })
    expect((await leerJornadaNoAbierta())?.estado).toBe('ENTREGADA')
  })

  it('cuando el servidor informa EN_RENDICION, ese estado reemplaza a ENTREGADA', async () => {
    await terminarElDia(entrada('op-m2'))

    await marcarJornadaNoAbierta(J1, 'EN_RENDICION', new Date('2026-11-04T19:00:00.000Z'))

    expect((await leerJornadaNoAbierta())?.estado).toBe('EN_RENDICION')
  })

  it('un «desconocido» no pisa ENTREGADA', async () => {
    await terminarElDia(entrada('op-m3'))

    await marcarJornadaNoAbierta(J1, 'DESCONOCIDO', new Date('2026-11-04T19:00:00.000Z'))

    expect((await leerJornadaNoAbierta())?.estado).toBe('ENTREGADA')
  })
})
