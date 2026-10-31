import 'fake-indexeddb/auto'

import Dexie from 'dexie'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Change 21, tarea 5.1 (`design.md` D10; `02` §13.2): la base local pasa a la versión 2 con las
 * tablas maestras y `meta`, conservando el `dispositivo_id` de una base v1.
 */
const TABLAS_MAESTRAS = [
  'sesion',
  'configuracion',
  'productos',
  'presentaciones',
  'clientes',
  'listas',
  'versiones',
  'precios',
  'reglas_descuento',
  'stock',
  'autorizadores',
  'catalogos',
]

describe('base local Dexie v2 (change 21, tarea 5.1)', () => {
  beforeEach(async () => {
    vi.resetModules()
    await Dexie.delete('distribuidora')
  })

  afterEach(async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    baseLocal.close()
    await Dexie.delete('distribuidora')
  })

  it('abre en versión 2 con las tablas maestras y meta', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(2)
    const nombres = baseLocal.tables.map((t) => t.name)
    for (const tabla of [...TABLAS_MAESTRAS, 'meta']) {
      expect(nombres).toContain(tabla)
    }
  })

  it('no crea todavía las tablas de operaciones del change 22a', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    const nombres = baseLocal.tables.map((t) => t.name)
    for (const tabla of ['ventas', 'cobranzas', 'movimientos_locales', 'cola']) {
      expect(nombres).not.toContain(tabla)
    }
  })

  it('una base v1 con dispositivo_id sube a v2 conservándolo (02 §12.2)', async () => {
    const v1 = new Dexie('distribuidora')
    v1.version(1).stores({ meta: 'clave' })
    await v1.open()
    await v1.table('meta').put({ clave: 'dispositivo_id', valor: 'disp-existente' })
    v1.close()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(2)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-existente')
  })
})
