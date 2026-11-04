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

const TABLAS_DE_OPERACIONES = ['ventas', 'cobranzas', 'movimientos_locales', 'cola', 'intentos_pin', 'anulaciones']

describe('base local Dexie v5 (change 21, tarea 5.1; change 22a, tarea 1.1; change 22d, tarea 5.1)', () => {
  beforeEach(async () => {
    vi.resetModules()
    await Dexie.delete('distribuidora')
  })

  afterEach(async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    baseLocal.close()
    await Dexie.delete('distribuidora')
  })

  it('abre en versión 5 con las tablas maestras, meta y las de operaciones', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(5)
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

  it('una base v2 con sesión, PIN, dispositivo_id y maestros abre en v5 sin perderlos (INV-01)', async () => {
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

    expect(baseLocal.verno).toBe(5)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-v2')
    expect((await baseLocal.meta.get('pin_derivacion'))?.valor).toBe('derivacion-x')
    expect(await baseLocal.table('sesion').get('actual')).toBeDefined()
    expect(await baseLocal.productos.get('p1')).toBeDefined()
    expect(await baseLocal.clientes.get('c1')).toBeDefined()
    for (const tabla of TABLAS_DE_OPERACIONES) {
      expect(await baseLocal.table(tabla).count()).toBe(0)
    }
  })

  it('una base v1 con dispositivo_id sube a v5 conservándolo (02 §12.2)', async () => {
    const v1 = new Dexie('distribuidora')
    v1.version(1).stores({ meta: 'clave' })
    await v1.open()
    await v1.table('meta').put({ clave: 'dispositivo_id', valor: 'disp-existente' })
    v1.close()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(5)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-existente')
  })
})

/**
 * Change 22d, tarea 5.1 (spec `sync/base-local`, «La base local guarda las anulaciones del
 * dispositivo»; `design.md` D6; cita SYN-09, INV-05, `02` §13.2, §13.4).
 */
describe('tabla de anulaciones (Dexie v4, change 22d)', () => {
  beforeEach(async () => {
    vi.resetModules()
    await Dexie.delete('distribuidora')
  })

  afterEach(async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    baseLocal.close()
    await Dexie.delete('distribuidora')
  })

  it('anulaciones tiene venta_id como clave y operation_id único, jornada_id y estado_envio como índices', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    const tabla = baseLocal.table('anulaciones')
    expect(tabla.schema.primKey.name).toBe('venta_id')
    const operationId = tabla.schema.indexes.find((i) => i.name === 'operation_id')
    expect(operationId?.unique).toBe(true)
    expect(tabla.schema.indexes.map((i) => i.name)).toEqual(expect.arrayContaining(['jornada_id', 'estado_envio']))
  })

  it('una base v3 con sesión, PIN, datos y dos ventas con su cola abre en v5 sin perder nada y con anulaciones vacía (SYN-09)', async () => {
    const v3 = new Dexie('distribuidora')
    v3.version(1).stores({ meta: 'clave' })
    v3.version(2).stores({
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
    v3.version(3).stores({
      ventas: 'venta_id, operation_id, jornada_id, estado_envio, numero',
      cobranzas: 'cobranza_id, venta_id',
      movimientos_locales: '++id, operation_id, [jornada_id+producto_id], [jornada_id+cliente_id]',
      cola: 'secuencia, &operation_id, estado',
      intentos_pin: '[usuario_id+autorizador_id]',
    })
    await v3.open()
    await v3.table('meta').bulkPut([
      { clave: 'dispositivo_id', valor: 'disp-v3' },
      { clave: 'pin_derivacion', valor: 'derivacion-y' },
      { clave: 'ultima_secuencia', valor: '2' },
    ])
    await v3.table('sesion').put({ clave: 'actual', usuario: { id: 'u1' } })
    await v3.table('productos').put({ id: 'p1', nombre: 'Vino A' })
    await v3.table('ventas').bulkPut([
      { venta_id: 'v1', operation_id: 'op-1', jornada_id: 'j1', estado_envio: 'PENDIENTE', numero: '0001-000008' },
      { venta_id: 'v2', operation_id: 'op-2', jornada_id: 'j1', estado_envio: 'ACEPTADA', numero: '0001-000009' },
    ])
    await v3.table('cola').bulkPut([
      { secuencia: 1, operation_id: 'op-1', estado: 'PENDIENTE' },
      { secuencia: 2, operation_id: 'op-2', estado: 'ACEPTADO' },
    ])
    await v3.table('movimientos_locales').add({ operation_id: 'op-1', jornada_id: 'j1', producto_id: 'p1' })
    v3.close()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(5)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-v3')
    expect((await baseLocal.meta.get('pin_derivacion'))?.valor).toBe('derivacion-y')
    expect(await baseLocal.sesion.get('actual')).toBeDefined()
    expect(await baseLocal.productos.get('p1')).toBeDefined()
    expect(await baseLocal.ventas.count()).toBe(2)
    expect((await baseLocal.cola.orderBy('secuencia').toArray()).map((c) => c.estado)).toEqual(['PENDIENTE', 'ACEPTADO'])
    expect(await baseLocal.movimientos_locales.count()).toBe(1)
    expect(await baseLocal.table('anulaciones').count()).toBe(0)
  })

  it('anulaciones no es una tabla maestra: el bootstrap no la toca (INV-05, 02 §13.4)', async () => {
    const { TABLAS_MAESTRAS: maestras } = await import('../../../../src/lib/dispositivo/db')
    expect(maestras as readonly string[]).not.toContain('anulaciones')
  })
})

/**
 * Change 23, tarea 3.1 (spec `sync/base-local`, «La base local guarda las cobranzas independientes
 * del dispositivo»; `design.md` D5; cita INV-05, SYN-09, `02` §13.2, §13.4): la v5 solo agrega
 * índices a `cobranzas` (`operation_id`, `cliente_id`, `jornada_id`, `estado_envio`) y no pierde
 * nada de una v4; los cobros viejos se leen como el cobro de su venta.
 */
describe('cobranzas independientes (Dexie v5, change 23)', () => {
  beforeEach(async () => {
    vi.resetModules()
    await Dexie.delete('distribuidora')
  })

  afterEach(async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    baseLocal.close()
    await Dexie.delete('distribuidora')
  })

  async function crearBaseV4(): Promise<void> {
    const v4 = new Dexie('distribuidora')
    v4.version(1).stores({ meta: 'clave' })
    v4.version(2).stores({
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
    v4.version(3).stores({
      ventas: 'venta_id, operation_id, jornada_id, estado_envio, numero',
      cobranzas: 'cobranza_id, venta_id',
      movimientos_locales: '++id, operation_id, [jornada_id+producto_id], [jornada_id+cliente_id]',
      cola: 'secuencia, &operation_id, estado',
      intentos_pin: '[usuario_id+autorizador_id]',
    })
    v4.version(4).stores({
      anulaciones: 'venta_id, &operation_id, jornada_id, estado_envio',
    })
    await v4.open()
    await v4.table('meta').bulkPut([
      { clave: 'dispositivo_id', valor: 'disp-v4' },
      { clave: 'pin_derivacion', valor: 'derivacion-z' },
      { clave: 'ultima_secuencia', valor: '3' },
    ])
    await v4.table('sesion').put({ clave: 'actual', usuario: { id: 'u1' } })
    await v4.table('productos').put({ id: 'p1', nombre: 'Vino A' })
    await v4.table('ventas').bulkPut([
      { venta_id: 'v1', operation_id: 'op-1', jornada_id: 'j1', estado_envio: 'PENDIENTE', numero: '0001-000008' },
      { venta_id: 'v2', operation_id: 'op-2', jornada_id: 'j1', estado_envio: 'ACEPTADA', numero: '0001-000009' },
    ])
    await v4.table('cobranzas').bulkPut([
      { cobranza_id: 'c1', venta_id: 'v1', operation_id: 'op-1', jornada_id: 'j1', medios: [], total: '1000.00' },
      { cobranza_id: 'c2', venta_id: 'v2', operation_id: 'op-2', jornada_id: 'j1', medios: [], total: '2000.00' },
    ])
    await v4.table('anulaciones').put({ venta_id: 'v2', operation_id: 'op-3', jornada_id: 'j1', estado_envio: 'PENDIENTE' })
    await v4.table('cola').bulkPut([
      { secuencia: 1, operation_id: 'op-1', estado: 'PENDIENTE' },
      { secuencia: 2, operation_id: 'op-2', estado: 'ACEPTADO' },
      { secuencia: 3, operation_id: 'op-3', estado: 'PENDIENTE' },
    ])
    await v4.table('movimientos_locales').add({ operation_id: 'op-1', jornada_id: 'j1', producto_id: 'p1' })
    v4.close()
  }

  it('cobranzas suma los índices operation_id, cliente_id, jornada_id y estado_envio sin quitar venta_id', async () => {
    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    const tabla = baseLocal.table('cobranzas')
    expect(tabla.schema.primKey.name).toBe('cobranza_id')
    expect(tabla.schema.indexes.map((i) => i.name)).toEqual(
      expect.arrayContaining(['venta_id', 'operation_id', 'cliente_id', 'jornada_id', 'estado_envio']),
    )
  })

  it('una base v4 con sesión, PIN, datos, dos ventas con cobro, una anulación y la cola abre en v5 sin perder nada (SYN-09)', async () => {
    await crearBaseV4()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    expect(baseLocal.verno).toBe(5)
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-v4')
    expect((await baseLocal.meta.get('pin_derivacion'))?.valor).toBe('derivacion-z')
    expect(await baseLocal.sesion.get('actual')).toBeDefined()
    expect(await baseLocal.productos.get('p1')).toBeDefined()
    expect(await baseLocal.ventas.count()).toBe(2)
    expect(await baseLocal.anulaciones.count()).toBe(1)
    expect((await baseLocal.cola.orderBy('secuencia').toArray()).map((c) => c.estado)).toEqual([
      'PENDIENTE',
      'ACEPTADO',
      'PENDIENTE',
    ])
    expect(await baseLocal.movimientos_locales.count()).toBe(1)
    expect(await baseLocal.cobranzas.count()).toBe(2)
  })

  it('los cobros guardados antes de la v5 siguen intactos y se buscan por su venta y por su operación', async () => {
    await crearBaseV4()

    const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
    await baseLocal.open()

    const deLaVenta = await baseLocal.cobranzas.where('venta_id').equals('v2').toArray()
    expect(deLaVenta).toEqual([
      { cobranza_id: 'c2', venta_id: 'v2', operation_id: 'op-2', jornada_id: 'j1', medios: [], total: '2000.00' },
    ])
    // Una fila sin `origen` es el cobro de su venta (D5): nadie la reescribió al subir de versión.
    expect(deLaVenta[0]).not.toHaveProperty('origen')
    expect((await baseLocal.cobranzas.where('operation_id').equals('op-1').first())?.cobranza_id).toBe('c1')
  })

  it('cobranzas no es una tabla maestra: el bootstrap y el cierre de sesión no la tocan (INV-05, 02 §13.4)', async () => {
    const { TABLAS_MAESTRAS: maestras } = await import('../../../../src/lib/dispositivo/db')
    expect(maestras as readonly string[]).not.toContain('cobranzas')
  })
})
