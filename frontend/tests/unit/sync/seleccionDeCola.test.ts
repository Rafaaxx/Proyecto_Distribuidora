import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import { partirEnLotes, seleccionarCola, TAMANO_DE_LOTE } from '../../../src/sync/seleccionDeCola'
import { comandoDePrueba, sembrarComando } from '../utils/colaDePrueba'

/**
 * Change 22b, tarea 1.2 (spec `sync/motor-de-sincronizacion`, «El teléfono envía solo la cola
 * propia, en orden y por lotes»; `design.md` D1; cita SYN-03, RUT-09, `02` §6.4).
 */
describe('selección de la cola propia (tarea 1.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('elige solo los PENDIENTE del usuario y del dispositivo, de cualquier jornada, por secuencia', async () => {
    await sembrarComando(comandoDePrueba(5, { jornadaId: 'j2' }))
    await sembrarComando(comandoDePrueba(2, { jornadaId: 'j1' }))
    await sembrarComando(comandoDePrueba(3, { usuarioId: 'otro' }))
    await sembrarComando(comandoDePrueba(4, { dispositivoId: 'd-ajeno' }))
    await sembrarComando(comandoDePrueba(1, { estado: 'ACEPTADO' }))
    await sembrarComando(comandoDePrueba(6, { estado: 'ACEPTADO_CON_OBSERVACIONES' }))

    const cola = await seleccionarCola('u1', 'd1')

    expect(cola.map((c) => c.secuencia)).toEqual([2, 5])
  })

  it('un RECHAZADO no se elige: no se vuelve a enviar solo', async () => {
    await sembrarComando(comandoDePrueba(1, { estado: 'RECHAZADO' }))
    await sembrarComando(comandoDePrueba(2))

    expect((await seleccionarCola('u1', 'd1')).map((c) => c.secuencia)).toEqual([2])
  })

  it('sin comandos propios devuelve una cola vacía', async () => {
    await sembrarComando(comandoDePrueba(1, { usuarioId: 'otro' }))

    expect(await seleccionarCola('u1', 'd1')).toEqual([])
  })

  it('parte en lotes de 50: 120 → 50, 50, 20; 50 → un lote; 0 → ninguno', () => {
    const cola = Array.from({ length: 120 }, (_, i) => comandoDePrueba(i + 1))

    expect(TAMANO_DE_LOTE).toBe(50)
    expect(partirEnLotes(cola).map((l) => l.length)).toEqual([50, 50, 20])
    expect(partirEnLotes(cola.slice(0, 50)).map((l) => l.length)).toEqual([50])
    expect(partirEnLotes([])).toEqual([])
    expect(partirEnLotes(cola)[1]?.[0]?.secuencia).toBe(51)
  })
})

describe('la base v3 del 22a abre igual con los estados ampliados (sin version(4))', () => {
  it('una fila PENDIENTE y una ACEPTADO conviven en el mismo almacén indexado por estado', async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await baseLocal.cola.bulkPut([comandoDePrueba(1), comandoDePrueba(2, { estado: 'ACEPTADO' })])

    expect(baseLocal.verno).toBe(3)
    expect(await baseLocal.cola.where('estado').equals('ACEPTADO').count()).toBe(1)
    expect(await baseLocal.cola.where('estado').equals('PENDIENTE').count()).toBe(1)
  })
})
