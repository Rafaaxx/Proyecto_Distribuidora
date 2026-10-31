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

const TABLAS_DE_OPERACIONES = ['ventas', 'cobranzas', 'movimientos_locales', 'cola', 'intentos_pin']

describe('base local Dexie v3 (change 21, tarea 5.1; change 22a, tarea 1.1)', () => {
  beforeEach(async () => {
    vi.resetModules()
    await Dexie.delete('distribuidora')
  })

  afterEach(async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    baseLocal.close()
    await Dexie.delete('distribuidora')
  })

  it('abre en versión 3 con las tablas maestras, meta y las de operaciones', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(3)
    const nombres = baseLocal.tables.map((t) => t.name)
    for (const tabla of [...TABLAS_MAESTRAS, 'meta', ...TABLAS_DE_OPERACIONES]) {
      expect(nombres).toContain(tabla)
    }
  })

  it('las tablas de operaciones tienen sus índices y operation_id es único en cola (INV-01, INV-03, INV-04)', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    const indices = (tabla: string) => baseLocal.table(tabla).schema.indexes.map((i) => i.name)
    expect(baseLocal.table('ventas').schema.primKey.name).toBe('venta_id')
    expect(indices('ventas')).toEqual(
      expect.arrayContaining(['jornada_id', 'estado_envio', 'numero', 'operation_id']),
    )
    expect(baseLocal.table('cobranzas').schema.primKey.name).toBe('cobranza_id')
    expect(indices('cobranzas')).toContain('venta_id')
    expect(baseLocal.table('movimientos_locales').schema.primKey.auto).toBe(true)
    expect(indices('movimientos_locales')).toEqual(
      expect.arrayContaining(['operation_id', '[jornada_id+producto_id]', '[jornada_id+cliente_id]']),
    )
    expect(baseLocal.table('cola').schema.primKey.name).toBe('secuencia')
    const operationId = baseLocal.table('cola').schema.indexes.find((i) => i.name === 'operation_id')
    expect(operationId?.unique).toBe(true)
    expect(indices('cola')).toContain('estado')
    expect(baseLocal.table('intentos_pin').schema.primKey.keyPath).toEqual(['usuario_id', 'autorizador_id'])
  })

  it('TABLAS_MAESTRAS no incluye ninguna tabla de operaciones (INV-01, SYN-09)', async () => {
    const { TABLAS_MAESTRAS: maestras } = await import('../../../../src/lib/dispositivo/db')
    for (const tabla of TABLAS_DE_OPERACIONES) {
      expect(maestras as readonly string[]).not.toContain(tabla)
    }
    expect(maestras).toHaveLength(TABLAS_MAESTRAS.length)
  })

  it('una base v2 con sesión, PIN, dispositivo_id y maestros abre en v3 sin perderlos (INV-01)', async () => {
    const v2 = new Dexie('distribuidora')
    v2.version(2).stores({
      meta: 'clave',
      sesion: 'clave',
      configuracion: 'clave',
      productos: 'id',
      presentaciones: 'id, producto_id',
      clientes: 'id',
      listas: 'id',
      versiones: 'id, lista_id',
      precios: '[version_id+producto_id], version_id',
      reglas_descuento: 'id',
      stock: 'producto_id',
      autorizadores: 'id',
      catalogos: 'clave',
    })
    await v2.open()
    await v2.table('meta').bulkPut([
      { clave: 'dispositivo_id', valor: 'disp-v2' },
      { clave: 'pin_derivacion', valor: 'derivacion-x' },
    ])
    await v2.table('sesion').put({ clave: 'actual', usuario: { id: 'u1' } })
    await v2.table('productos').put({ id: 'p1', nombre: 'Vino A' })
    await v2.table('clientes').put({ id: 'c1', nombre: 'Kiosco' })
    v2.close()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(3)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-v2')
    expect((await baseLocal.meta.get('pin_derivacion'))?.valor).toBe('derivacion-x')
    expect(await baseLocal.table('sesion').get('actual')).toBeDefined()
    expect(await baseLocal.productos.get('p1')).toBeDefined()
    expect(await baseLocal.clientes.get('c1')).toBeDefined()
    for (const tabla of TABLAS_DE_OPERACIONES) {
      expect(await baseLocal.table(tabla).count()).toBe(0)
    }
  })

  it('una base v1 con dispositivo_id sube a v3 conservándolo (02 §12.2)', async () => {
    const v1 = new Dexie('distribuidora')
    v1.version(1).stores({ meta: 'clave' })
    await v1.open()
    await v1.table('meta').put({ clave: 'dispositivo_id', valor: 'disp-existente' })
    v1.close()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(3)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-existente')
  })
})
