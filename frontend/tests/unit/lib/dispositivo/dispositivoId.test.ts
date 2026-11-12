import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

/**
 * `docs/02-arquitectura.md` §12.2: "En el primer inicio, la aplicación
 * genera un `dispositivo_id` y lo guarda en IndexedDB. El login lo envía".
 * Tarea 13.6.
 */
describe('identificador de dispositivo generado en el primer arranque (tarea 13.6)', () => {
  beforeEach(async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.meta.clear()
  })

  it('genera un identificador válido en el primer arranque y lo persiste en IndexedDB', async () => {
    const { obtenerOGenerarDispositivoId } = await import(
      '../../../../src/lib/dispositivo/dispositivoId'
    )
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')

    const id = await obtenerOGenerarDispositivoId()

    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)
    const registrado = await baseLocal.meta.get('dispositivo_id')
    expect(registrado?.valor).toBe(id)
  })

  it('reutiliza el mismo identificador en arranques posteriores', async () => {
    const { obtenerOGenerarDispositivoId } = await import(
      '../../../../src/lib/dispositivo/dispositivoId'
    )

    const primero = await obtenerOGenerarDispositivoId()
    const segundo = await obtenerOGenerarDispositivoId()

    expect(segundo).toBe(primero)
  })

  it('llamadas concurrentes en el primer arranque no generan dos identificadores distintos', async () => {
    const { obtenerOGenerarDispositivoId } = await import(
      '../../../../src/lib/dispositivo/dispositivoId'
    )
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')

    const [a, b] = await Promise.all([obtenerOGenerarDispositivoId(), obtenerOGenerarDispositivoId()])

    expect(a).toBe(b)
    const filas = await baseLocal.meta.toArray()
    expect(filas.filter((fila) => fila.clave === 'dispositivo_id')).toHaveLength(1)
  })
})
